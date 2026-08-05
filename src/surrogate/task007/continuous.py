"""Task007 M3 Level-A continuous objective-GP benchmark primitives.

The oracle in this module is the frozen Task006 Legendre-3 response model.  It
is deliberately a surrogate-oracle benchmark: no FEM or Task006 lock mutation
is possible here.  The continuous BO loop counts only actual oracle objective
evaluations as online queries; GP/acquisition evaluations are not oracle calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.stats import qmc

from .objective import (
    DOMAIN_MAX,
    DOMAIN_MIN,
    ObjectiveGP,
    canonical_hash,
    expected_improvement,
    initial_sets,
    scale_geometry,
)

from ..task006.dataset import load_dataset
from ..task006.design import TASK006_DATASET_ID
from ..task006.m2r import _fit_contract, _predict_fitted_contract


FORWARD_SOLVER_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE_SCHEMA = "task002.fixed-n0-orders.v3"
LOCK_REL = "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/TASK006_MODEL_SELECTION_LOCK.json"
TRAIN_ROOT_REL = "benchmarks/artifacts/cases/137_task006_train37_dataset/train37"
TASK006_SURROGATE_REL = "src/surrogate/task006/surrogate.py"
TASK006_M2R_REL = "src/surrogate/task006/m2r.py"
TASK006_LOCK_SHA256 = "f08180f891b485a4ddedcf4066a2bed6a4164342fc0e296bfb06d2278469a7a1"
TASK006_MANIFEST_SHA256 = "f36ffe992efe44f89c51bcac35e68145256e80979810d60ae5437686fd91cf84"
TASK006_EPSILON = 1.0e-15
M3_EI_SWITCH_THRESHOLD = 1.0e-3
M3_MAX_ONLINE_QUERIES = 20
M3_MAP_HEIGHT_TOLERANCE_NM = 0.25
M3_MAP_WIDTH_TOLERANCE_NM = 0.05
M3_MAP_GRID_SIZE = 161
M3_EI_GRID_SIZE = 61
CONTRACTS = ("J1", "J0")
NOISE_SCENARIOS = ("N1", "N2")

# Fixed off-grid points.  They are deliberately not members of the immutable
# 37-point train geometry set and are reused for every contract/noise scenario.
OFFGRID_TARGETS = (
    (116.2, 16.18), (116.2, 17.63), (117.9, 16.33), (118.7, 17.81),
    (119.6, 16.24), (120.4, 17.62), (121.3, 16.38), (122.1, 17.83),
    (123.0, 16.22), (123.8, 17.57), (124.4, 16.47), (124.7, 17.18),
)
NOISE_CONFIG = {
    "N1": {"relative": 0.01, "floor": 1.0e-4, "seed_base": 70000},
    "N2": {"relative": 0.02, "floor": 5.0e-4, "seed_base": 80000},
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def array_hash(value: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.float64))
    descriptor = json.dumps({"dtype": str(array.dtype), "shape": list(array.shape)},
                            sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(descriptor + array.tobytes(order="C")).hexdigest()


def noise_sigma(measurement: np.ndarray, scenario: str) -> np.ndarray:
    values = np.asarray(measurement, dtype=np.float64)
    config = NOISE_CONFIG[scenario]
    return np.sqrt((config["relative"] * np.abs(values)) ** 2 + config["floor"] ** 2)


def scale_to_domain(values: np.ndarray) -> np.ndarray:
    scaled = np.asarray(values, dtype=np.float64)
    return DOMAIN_MIN + (scaled + 1.0) * 0.5 * (DOMAIN_MAX - DOMAIN_MIN)


def within_map_tolerance(point: np.ndarray, map_point: np.ndarray) -> bool:
    delta = np.abs(np.asarray(point, dtype=np.float64) - np.asarray(map_point, dtype=np.float64))
    return bool(delta[0] <= M3_MAP_HEIGHT_TOLERANCE_NM and delta[1] <= M3_MAP_WIDTH_TOLERANCE_NM)


class Legendre3ResponseOracle:
    """Frozen Task006 M2R Legendre-3 response model as a continuous oracle."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.dataset_root = self.repo_root / TRAIN_ROOT_REL
        self.lock_path = self.repo_root / LOCK_REL
        self.lock_sha256 = file_sha256(self.lock_path)
        if self.lock_sha256 != TASK006_LOCK_SHA256:
            raise ValueError("Task006 model lock hash changed")
        lock = json.loads(self.lock_path.read_text())
        if lock.get("status") != "locked_for_blind" or lock.get("selected_candidate") != "legendre_3":
            raise ValueError("Task006 lock is not the frozen Legendre-3 lock")
        if lock.get("dataset_manifest_sha256") != TASK006_MANIFEST_SHA256:
            raise ValueError("Task006 manifest identity mismatch in lock")
        if lock.get("forward_solver_sha") != FORWARD_SOLVER_SHA or lock.get("model_id") != MODEL_ID:
            raise ValueError("Task006 forward identity mismatch in lock")
        data = load_dataset(self.dataset_root)
        self.geometry = np.asarray(data["geometries"], dtype=np.float64)
        self.latent = np.asarray(data["aggregate_latent"], dtype=np.float64)
        self.fractions = np.asarray(data["s1_fractions"], dtype=np.float64)
        if self.geometry.shape != (37, 2):
            raise ValueError("frozen train37 geometry shape mismatch")
        if file_sha256(self.dataset_root / "dataset_manifest.json") != TASK006_MANIFEST_SHA256:
            raise ValueError("Task006 train37 manifest changed")
        fit = _fit_contract(
            "legendre_3", self.geometry, self.latent, self.fractions,
            np.arange(len(self.geometry), dtype=np.int64), self.geometry, seed=0,
        )
        self._models = fit["_models"]
        self.fit_records = fit["fits"]

    def predict(self, geometry: np.ndarray) -> dict[str, np.ndarray]:
        query = np.asarray(geometry, dtype=np.float64).reshape(-1, 2)
        if np.any(query < DOMAIN_MIN[None, :]) or np.any(query > DOMAIN_MAX[None, :]):
            raise ValueError("oracle query outside frozen geometry domain")
        block = _predict_fitted_contract(self._models, query)
        # J0 is aggregate R/T; J1 is selected m=0 order-total power.  Both are
        # flattened angle-major, exactly as Task007 V1's objective contract.
        return {
            "J1": np.asarray(block["selected_prediction"], dtype=np.float64).reshape(len(query), 6),
            "J0": np.asarray(block["aggregate_prediction"][:, :, :2], dtype=np.float64).reshape(len(query), 6),
            "aggregate": np.asarray(block["aggregate_prediction"], dtype=np.float64),
            "selected": np.asarray(block["selected_prediction"], dtype=np.float64),
            "side_total_authority": np.asarray(block["side_total_authority"], dtype=np.float64),
            "ledger_residual": np.asarray(block["ledger_residual"], dtype=np.float64),
        }

    def metadata(self) -> dict[str, Any]:
        return {
            "oracle_kind": "surrogate_oracle_algorithm_benchmark",
            "candidate": "legendre_3",
            "dataset_id": TASK006_DATASET_ID,
            "dataset_manifest_sha256": TASK006_MANIFEST_SHA256,
            "model_lock_sha256": self.lock_sha256,
            "forward_solver_sha": FORWARD_SOLVER_SHA,
            "model_id": MODEL_ID,
            "solver_route_id": ROUTE_ID,
            "observable_schema_version": OBSERVABLE_SCHEMA,
            "task006_surrogate_source_sha256": file_sha256(self.repo_root / TASK006_SURROGATE_REL),
            "task006_m2r_source_sha256": file_sha256(self.repo_root / TASK006_M2R_REL),
            "train_geometry_hash": array_hash(self.geometry),
            "fit_count": len(self.fit_records),
            "fit_records": self.fit_records,
            "s0_contract": "Legendre-3 aggregate_latent zR/zT then softmax(zR,zT,0)",
            "s1_contract": "S0 side-total authority times Legendre-3 selected-fraction sigmoid",
            "new_fem_count": 0,
            "task006_lock_modified": False,
        }


def objective_values(oracle: Legendre3ResponseOracle, points: np.ndarray,
                    measurement: np.ndarray, contract: str, scenario: str) -> np.ndarray:
    response = oracle.predict(np.asarray(points, dtype=np.float64))[contract]
    target = np.asarray(measurement, dtype=np.float64)
    sigma = noise_sigma(target, scenario)
    residual = (response - target[None, :]) / sigma[None, :]
    return 0.5 * np.sum(residual * residual, axis=1)


def objective_scalar(oracle: Legendre3ResponseOracle, point: np.ndarray,
                    measurement: np.ndarray, contract: str, scenario: str) -> float:
    return float(objective_values(oracle, np.asarray(point, dtype=np.float64).reshape(1, 2),
                                  measurement, contract, scenario)[0])


def generate_sobol37(seed: int = 7007) -> np.ndarray:
    sampler = qmc.Sobol(d=2, scramble=True, seed=seed)
    unit = sampler.random_base2(m=6)[:37]
    return DOMAIN_MIN[None, :] + unit * (DOMAIN_MAX - DOMAIN_MIN)[None, :]


def compact_gp_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    selected = metadata.get("selected") or {}
    runs = selected.get("optimization_runs", [])
    warnings = sum(int(row.get("warning_count", 0)) for row in runs)
    collisions = sum(len(row.get("boundary_collisions", [])) for row in runs)
    candidate_lml = []
    for candidate in metadata.get("jitter_candidates_metadata", []):
        candidate_lml.append({
            "jitter": candidate.get("jitter"),
            "lml": candidate.get("metadata", {}).get("log_marginal_likelihood"),
            "warning_count": sum(int(row.get("warning_count", 0)) for row in candidate.get("metadata", {}).get("optimization_runs", [])),
            "boundary_collision_count": sum(len(row.get("boundary_collisions", [])) for row in candidate.get("metadata", {}).get("optimization_runs", [])),
        })
    return {
        "kernel": metadata.get("kernel"), "optimizer_starts": metadata.get("optimizer_starts"),
        "jitter_candidates": metadata.get("jitter_candidates"),
        "selected_jitter": metadata.get("selected_jitter"),
        "selected_fitted_kernel": selected.get("fitted_kernel"),
        "selected_lml": selected.get("log_marginal_likelihood"),
        "selected_start": selected.get("selected_start"),
        "selected_warning_count": warnings,
        "selected_boundary_collision_count": collisions,
        "candidate_lml": candidate_lml,
        "optimizer_statuses": [row.get("optimizer_status") for row in runs],
    }


def _best_row(points: np.ndarray, values: np.ndarray, map_point: np.ndarray,
              map_f: float, online_query_count: int) -> dict[str, Any]:
    index = int(np.argmin(values))
    point = np.asarray(points[index], dtype=np.float64)
    return {
        "online_query_count": int(online_query_count),
        "best_evaluated_geometry": point.tolist(),
        "best_evaluated_F": float(values[index]),
        "best_evaluated_log10F": float(np.log10(values[index] + 1.0e-12)),
        "distance_to_oracle_MAP_nm": float(np.linalg.norm(point - map_point)),
        "height_abs_error_to_MAP_nm": float(abs(point[0] - map_point[0])),
        "width_abs_error_to_MAP_nm": float(abs(point[1] - map_point[1])),
        "within_MAP_tolerance": within_map_tolerance(point, map_point),
        "oracle_MAP_F": float(map_f),
    }


def oracle_continuous_map(oracle: Legendre3ResponseOracle, measurement: np.ndarray,
                          contract: str, scenario: str,
                          grid_size: int = M3_MAP_GRID_SIZE) -> dict[str, Any]:
    axis_h = np.linspace(DOMAIN_MIN[0], DOMAIN_MAX[0], grid_size)
    axis_w = np.linspace(DOMAIN_MIN[1], DOMAIN_MAX[1], grid_size)
    grid = np.asarray([(h, w) for h in axis_h for w in axis_w], dtype=np.float64)
    grid_values = objective_values(oracle, grid, measurement, contract, scenario)
    starts = grid[np.argsort(grid_values, kind="mergesort")[:16]]
    starts = np.vstack((starts, np.asarray([
        [DOMAIN_MIN[0], DOMAIN_MIN[1]], [DOMAIN_MIN[0], DOMAIN_MAX[1]],
        [DOMAIN_MAX[0], DOMAIN_MIN[1]], [DOMAIN_MAX[0], DOMAIN_MAX[1]],
        [(DOMAIN_MIN[0] + DOMAIN_MAX[0]) / 2, (DOMAIN_MIN[1] + DOMAIN_MAX[1]) / 2],
    ])))
    local_rows: list[dict[str, Any]] = []
    best_result = None
    for start in starts:
        result = minimize(
            lambda point: objective_scalar(oracle, point, measurement, contract, scenario),
            np.asarray(start, dtype=np.float64), method="L-BFGS-B",
            bounds=((float(DOMAIN_MIN[0]), float(DOMAIN_MAX[0])),
                    (float(DOMAIN_MIN[1]), float(DOMAIN_MAX[1]))),
            options={"maxiter": 500, "ftol": 1.0e-14, "gtol": 1.0e-10},
        )
        row = {
            "start": np.asarray(start).tolist(), "x": np.asarray(result.x).tolist(),
            "fun": float(result.fun), "success": bool(result.success),
            "status": int(result.status), "message": str(result.message), "nit": int(result.nit),
        }
        local_rows.append(row)
        if best_result is None or float(result.fun) < float(best_result.fun):
            best_result = result
    if best_result is None:
        raise RuntimeError("oracle MAP optimizer produced no result")
    map_point = np.asarray(best_result.x, dtype=np.float64)
    return {
        "contract": contract, "noise_scenario": scenario,
        "grid_size": int(grid_size), "grid_min_geometry": grid[int(np.argmin(grid_values))].tolist(),
        "grid_min_F": float(np.min(grid_values)), "optimizer_runs": local_rows,
        "all_optimizer_success": bool(all(row["success"] for row in local_rows)),
        "map_geometry": map_point.tolist(), "map_F": float(best_result.fun),
        "map_log10F": float(np.log10(float(best_result.fun) + 1.0e-12)),
        "map_not_forced_to_hidden_truth": True,
    }


def _continuous_acquisition(gp: ObjectiveGP, observed: np.ndarray, best_log10f: float,
                            seed: int) -> dict[str, Any]:
    axis = np.linspace(-1.0, 1.0, M3_EI_GRID_SIZE)
    grid = np.asarray([(h, w) for h in axis for w in axis], dtype=np.float64)
    mean, std = gp.predict(grid, return_std=True)
    ei = expected_improvement(mean, std, best_log10f)
    order = np.argsort(-ei, kind="mergesort")
    local_rows: list[dict[str, Any]] = []
    candidates: list[tuple[float, np.ndarray, str]] = []
    for index in order[:8]:
        start = grid[int(index)]
        result = minimize(
            lambda point: -float(expected_improvement(
                np.asarray(gp.predict(np.asarray(point).reshape(1, 2))),
                np.asarray(gp.predict(np.asarray(point).reshape(1, 2), return_std=True)[1]),
                best_log10f)[0]),
            start, method="L-BFGS-B", bounds=((-1.0, 1.0), (-1.0, 1.0)),
            options={"maxiter": 100, "ftol": 1.0e-12, "gtol": 1.0e-10},
        )
        point = np.asarray(result.x, dtype=np.float64)
        point_mean, point_std = gp.predict(point.reshape(1, 2), return_std=True)
        point_ei = float(expected_improvement(point_mean, point_std, best_log10f)[0])
        candidates.append((point_ei, point, "continuous_EI"))
        local_rows.append({"start": start.tolist(), "x": point.tolist(), "ei": point_ei,
                           "success": bool(result.success), "status": int(result.status),
                           "message": str(result.message), "nit": int(result.nit)})
    grid_best = float(ei[int(order[0])])
    selected = max(candidates, key=lambda item: (item[0], -item[1][0], -item[1][1]))
    fallback = False
    fallback_rows: list[dict[str, Any]] = []
    if grid_best < M3_EI_SWITCH_THRESHOLD:
        fallback = True
        mean_order = np.argsort(mean, kind="mergesort")[:8]
        for index in mean_order:
            start = grid[int(index)]
            result = minimize(
                lambda point: float(gp.predict(np.asarray(point).reshape(1, 2))[0]),
                start, method="L-BFGS-B", bounds=((-1.0, 1.0), (-1.0, 1.0)),
                options={"maxiter": 150, "ftol": 1.0e-12, "gtol": 1.0e-10},
            )
            point = np.asarray(result.x, dtype=np.float64)
            local_mean = float(gp.predict(point.reshape(1, 2))[0])
            fallback_rows.append({"start": start.tolist(), "x": point.tolist(), "posterior_mean": local_mean,
                                  "success": bool(result.success), "status": int(result.status),
                                  "message": str(result.message), "nit": int(result.nit)})
        if fallback_rows:
            row = min(fallback_rows, key=lambda item: (item["posterior_mean"], item["x"][0], item["x"][1]))
            selected = (float(expected_improvement(
                *gp.predict(np.asarray(row["x"]).reshape(1, 2), return_std=True), best_log10f)[0]),
                        np.asarray(row["x"], dtype=np.float64), "bounded_local_refinement")
    return {
        "grid_best_ei": grid_best, "ei_switch_threshold": M3_EI_SWITCH_THRESHOLD,
        "fallback_used": fallback, "local_ei_optimizers": local_rows,
        "fallback_local_refinement": fallback_rows,
        "selected_scaled": selected[1].tolist(), "selected_geometry": scale_to_domain(selected[1]).tolist(),
        "selected_ei": float(selected[0]), "selected_mode": selected[2],
        "grid_candidate_count": len(grid), "candidate_order_hash": canonical_hash(order.tolist()),
        "acquisition_seed": int(seed),
    }


def _deduplicate(point: np.ndarray, observed: np.ndarray) -> tuple[np.ndarray, bool]:
    candidate = np.asarray(point, dtype=np.float64)
    if len(observed) == 0 or float(np.min(np.linalg.norm(observed - candidate[None, :], axis=1))) > 1.0e-8:
        return candidate, False
    for axis in (0, 1):
        direction = 1.0 if candidate[axis] < 1.0 else -1.0
        shifted = candidate.copy(); shifted[axis] = np.clip(shifted[axis] + direction * 1.0e-3, -1.0, 1.0)
        if float(np.min(np.linalg.norm(observed - shifted[None, :], axis=1))) > 1.0e-8:
            return shifted, True
    return candidate, True


def run_sequential_bo(oracle: Legendre3ResponseOracle, initial: np.ndarray,
                      measurement: np.ndarray, contract: str, scenario: str,
                      map_point: np.ndarray, map_f: float, seed: int,
                      max_online_queries: int = M3_MAX_ONLINE_QUERIES) -> dict[str, Any]:
    initial_points = np.asarray(initial, dtype=np.float64).reshape(-1, 2)
    initial_values = objective_values(oracle, initial_points, measurement, contract, scenario)
    observed_points = initial_points.copy()
    observed_values = initial_values.copy()
    history = [_best_row(observed_points, observed_values, map_point, map_f, 0)]
    queries: list[dict[str, Any]] = []
    gp_updates: list[dict[str, Any]] = []
    if history[-1]["within_MAP_tolerance"]:
        stop_reason = "initialization_already_in_MAP_tolerance"
    else:
        stop_reason = "max_online_queries"
        for step in range(max_online_queries):
            gp = ObjectiveGP(seed=seed + step * 31)
            x_scaled = scale_geometry(observed_points)
            y_log = np.log10(observed_values + 1.0e-12)
            gp.fit(x_scaled, y_log)
            gp_updates.append({"query_step": step, "observed_count": len(observed_points),
                               "observed_geometry_hash": array_hash(observed_points),
                               "metadata": compact_gp_metadata(gp.metadata())})
            acquisition = _continuous_acquisition(gp, x_scaled, float(np.min(y_log)), seed + step)
            selected_scaled, duplicate = _deduplicate(np.asarray(acquisition["selected_scaled"]), x_scaled)
            selected_geometry = scale_to_domain(selected_scaled)
            value = objective_scalar(oracle, selected_geometry, measurement, contract, scenario)
            observed_points = np.vstack((observed_points, selected_geometry))
            observed_values = np.append(observed_values, value)
            queries.append({
                "query_step": step, "geometry": selected_geometry.tolist(), "scaled_geometry": selected_scaled.tolist(),
                "objective_F": float(value), "objective_log10F": float(np.log10(value + 1.0e-12)),
                "acquisition": acquisition, "duplicate_resolution": bool(duplicate),
            })
            history.append(_best_row(observed_points, observed_values, map_point, map_f, step + 1))
            if history[-1]["within_MAP_tolerance"]:
                stop_reason = "entered_MAP_tolerance"
                break
    return {
        "method": "continuous_sequential_EI", "contract": contract, "noise_scenario": scenario,
        "seed": int(seed), "initial_count": int(len(initial_points)),
        "initial_points": initial_points.tolist(), "initial_objective_F": initial_values.tolist(),
        "initial_objective_log10F": np.log10(initial_values + 1.0e-12).tolist(),
        "initial_geometry_hash": array_hash(initial_points), "initial_target_leakage": False,
        "oracle_MAP_geometry": np.asarray(map_point).tolist(), "oracle_MAP_F": float(map_f),
        "queries": queries, "gp_updates": gp_updates, "history": history,
        "final": history[-1], "online_query_count": len(queries),
        "queries_to_MAP": next((row["online_query_count"] for row in history if row["within_MAP_tolerance"]), None),
        "stop_reason": stop_reason, "max_online_queries": int(max_online_queries),
    }


def run_random_search(oracle: Legendre3ResponseOracle, measurement: np.ndarray, contract: str,
                      scenario: str, map_point: np.ndarray, map_f: float, seed: int,
                      budget: int = 2000) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    points = DOMAIN_MIN[None, :] + rng.random((budget, 2)) * (DOMAIN_MAX - DOMAIN_MIN)[None, :]
    values = objective_values(oracle, points, measurement, contract, scenario)
    best = _best_row(points, values, map_point, map_f, budget)
    distances = np.linalg.norm(points - map_point[None, :], axis=1)
    map_hits = np.asarray([
        abs(point[0] - map_point[0]) <= M3_MAP_HEIGHT_TOLERANCE_NM
        and abs(point[1] - map_point[1]) <= M3_MAP_WIDTH_TOLERANCE_NM
        for point in points
    ])
    return {"method": "B0_random_continuous_search", "contract": contract, "noise_scenario": scenario,
            "seed": int(seed), "budget": int(budget), "points_hash": array_hash(points),
            "best": best, "queries_to_MAP": int(np.flatnonzero(map_hits)[0] + 1) if np.any(map_hits) else None,
            "minimum_distance_to_MAP_nm": float(np.min(distances)), "best_evaluated_geometry": best["best_evaluated_geometry"],
            "best_evaluated_F": best["best_evaluated_F"], "oracle_MAP_F": float(map_f)}


def run_multistart_local(oracle: Legendre3ResponseOracle, measurement: np.ndarray, contract: str,
                         scenario: str, map_point: np.ndarray, map_f: float, seed: int) -> dict[str, Any]:
    starts = np.asarray([[115.0, 16.0], [115.0, 18.0], [125.0, 16.0], [125.0, 18.0],
                         [120.0, 17.0], [117.5, 17.0], [122.5, 17.0], [120.0, 16.5]], dtype=np.float64)
    evaluations: list[list[float]] = []
    attempts: list[dict[str, Any]] = []
    best = None
    for start in starts:
        def fun(point: np.ndarray) -> float:
            value = objective_scalar(oracle, point, measurement, contract, scenario)
            evaluations.append([float(point[0]), float(point[1]), float(value)])
            return value
        result = minimize(fun, start, method="L-BFGS-B",
                          bounds=((float(DOMAIN_MIN[0]), float(DOMAIN_MAX[0])),
                                  (float(DOMAIN_MIN[1]), float(DOMAIN_MAX[1]))),
                          options={"maxiter": 150, "ftol": 1.0e-14, "gtol": 1.0e-10})
        attempts.append({"start": start.tolist(), "x": np.asarray(result.x).tolist(), "fun": float(result.fun),
                         "success": bool(result.success), "status": int(result.status), "message": str(result.message),
                         "nit": int(result.nit)})
        if best is None or float(result.fun) < float(best.fun):
            best = result
    if best is None:
        raise RuntimeError("multi-start local optimization returned no result")
    evaluated_points = np.asarray([[row[0], row[1]] for row in evaluations], dtype=np.float64)
    evaluated_values = np.asarray([row[2] for row in evaluations], dtype=np.float64)
    best_row = _best_row(evaluated_points, evaluated_values, map_point, map_f, len(evaluations))
    hits = [i + 1 for i, point in enumerate(evaluated_points)
            if within_map_tolerance(point, map_point)]
    return {"method": "B1_multistart_bounded_LBFGSB", "contract": contract, "noise_scenario": scenario,
            "seed": int(seed), "starts": starts.tolist(), "attempts": attempts,
            "evaluations": evaluations, "oracle_query_count": len(evaluations),
            "queries_to_MAP": min(hits) if hits else None, "best": best_row,
            "oracle_MAP_F": float(map_f), "optimizer_selected_geometry": np.asarray(best.x).tolist(),
            "optimizer_selected_F": float(best.fun)}


def initialization_sets(train_geometry: np.ndarray) -> dict[str, np.ndarray]:
    cold5_indices = initial_sets(train_geometry, 5, 6)[0]
    cold5 = np.asarray(train_geometry, dtype=np.float64)[cold5_indices]
    sobol37 = generate_sobol37()
    return {
        "cold5": np.asarray(cold5, dtype=np.float64),
        "sobol12": np.asarray(sobol37[:12], dtype=np.float64),
        "sobol37": np.asarray(sobol37, dtype=np.float64),
        "train37": np.asarray(train_geometry, dtype=np.float64),
    }


def compact_summary(rows: list[dict[str, Any]], method: str, contract: str, scenario: str) -> dict[str, Any]:
    q = [row["queries_to_MAP"] for row in rows if row.get("queries_to_MAP") is not None]
    final_hits = [bool(row["final"]["within_MAP_tolerance"]) for row in rows]
    return {
        "method": method, "contract": contract, "noise_scenario": scenario,
        "target_count": len(rows), "map_hit_count": int(sum(final_hits)),
        "map_hit_fraction": float(np.mean(final_hits)), "queries_to_MAP_hit_count": len(q),
        "median_queries_to_MAP": float(np.median(q)) if q else None,
        "p90_queries_to_MAP": float(np.percentile(q, 90)) if q else None,
        "max_queries_to_MAP": int(max(q)) if q else None,
        "all_hits_within_20": bool(len(q) == len(rows) and max(q, default=0) <= M3_MAX_ONLINE_QUERIES),
        "gate_pass": bool(sum(final_hits) >= 11 and q and float(np.median(q)) <= 8.0
                           and len(q) == len(rows) and max(q) <= M3_MAX_ONLINE_QUERIES),
    }
