"""Task007 scalar objective, replay inventory and deterministic BO primitives.

This module consumes only the immutable Task006 compact dataset and the eleven
complete Case141 stored samples.  It never calls a forward solver.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.optimize import minimize

from ..models import ExactARDGP


FORWARD_SOLVER_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE_SCHEMA = "task002.fixed-n0-orders.v3"
TRAIN_ROOT_REL = "benchmarks/artifacts/cases/137_task006_train37_dataset/train37"
LOCK_REL = "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/TASK006_MODEL_SELECTION_LOCK.json"
CASE141_ROOT_REL = "benchmarks/artifacts/cases/141_task006_blind12_forward/blind"
ANGLES = (("A05", 2.0, 0.0), ("A07", 2.0, 90.0), ("A09", 4.0, 60.0))
EXTERNAL_GEOMETRIES = (
    (117.5, 16.5), (117.5, 16.75), (117.5, 17.5),
    (118.75, 16.5), (118.75, 17.5),
    (121.25, 16.5), (121.25, 17.5),
    (122.5, 16.5), (122.5, 16.75), (122.5, 17.25), (122.5, 17.5),
)
EXCLUDED_GEOMETRY = (117.5, 17.25)
CONTRACTS = ("J1", "J0")
NOISE_SCENARIOS = ("N1", "N2")
EPSILON_F = 1.0e-12
DOMAIN_MIN = np.asarray([115.0, 16.0], dtype=np.float64)
DOMAIN_MAX = np.asarray([125.0, 18.0], dtype=np.float64)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return sha256_bytes(encoded)


def array_hash(value: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.float64))
    descriptor = json.dumps({"dtype": str(array.dtype), "shape": list(array.shape)},
                            sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(descriptor + array.tobytes(order="C"))


def scale_geometry(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    return 2.0 * (array - DOMAIN_MIN) / (DOMAIN_MAX - DOMAIN_MIN) - 1.0


def noise_sigma(measurement: np.ndarray, scenario: str) -> np.ndarray:
    values = np.asarray(measurement, dtype=np.float64)
    if scenario == "N1":
        return np.sqrt((0.01 * np.abs(values)) ** 2 + (1.0e-4) ** 2)
    if scenario == "N2":
        return np.sqrt((0.02 * np.abs(values)) ** 2 + (5.0e-4) ** 2)
    raise ValueError(f"unknown noise scenario: {scenario}")


def objective_values(measurement: np.ndarray, responses: np.ndarray,
                     scenario: str) -> np.ndarray:
    """Evaluate F(x|y_M), using sigma(y_M) as the frozen diagonal weight."""
    target = np.asarray(measurement, dtype=np.float64)
    values = np.asarray(responses, dtype=np.float64)
    if target.ndim != 1 or values.ndim != 2 or values.shape[1] != target.size:
        raise ValueError("objective shapes disagree")
    sigma = noise_sigma(target, scenario)
    residual = (values - target[None, :]) / sigma[None, :]
    return 0.5 * np.sum(residual * residual, axis=1)


def log_objective(values: np.ndarray) -> np.ndarray:
    return np.log10(np.asarray(values, dtype=np.float64) + EPSILON_F)


def _json_sample(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _m0_values(sample: dict[str, Any]) -> tuple[float, float]:
    orders = sample.get("mother_response", {}).get("orders", [])
    selected: dict[str, dict[str, Any]] = {}
    for side in ("reflection", "transmission"):
        matches = [row for row in orders
                   if row.get("side") == side and int(row.get("m")) == 0
                   and int(row.get("n")) == 0]
        if len(matches) != 1:
            raise ValueError(f"m=0 channel is not unique for {side}")
        row = matches[0]
        if row.get("power_carrying") is not True or row.get("order_total_power") is None:
            raise ValueError(f"m=0 channel is not power-carrying for {side}")
        selected[side] = row
    return float(selected["reflection"]["order_total_power"]), float(selected["transmission"]["order_total_power"])


def _validate_sample(sample: dict[str, Any], geometry: tuple[float, float],
                     angle_id: str, grazing: float, azimuth: float) -> None:
    h, w = geometry
    if sample.get("status") != "measured_pass":
        raise ValueError(f"sample is not measured_pass: {geometry}/{angle_id}")
    if sample.get("source_sha") != FORWARD_SOLVER_SHA or sample.get("source_dirty") is not False:
        raise ValueError(f"source identity mismatch: {geometry}/{angle_id}")
    if sample.get("model_id") != MODEL_ID or sample.get("solver_route_id") != ROUTE_ID:
        raise ValueError(f"model identity mismatch: {geometry}/{angle_id}")
    if sample.get("observable_schema_version") != OBSERVABLE_SCHEMA:
        raise ValueError(f"observable identity mismatch: {geometry}/{angle_id}")
    if sample.get("inputs") != [h, w, grazing, azimuth]:
        raise ValueError(f"input mismatch: {geometry}/{angle_id}")
    rta = sample.get("aggregates", {})
    for key in ("R_total", "T_total", "A_balance"):
        if not np.isfinite(float(rta[key])):
            raise ValueError(f"nonfinite aggregate: {geometry}/{angle_id}")
    if abs(float(rta["A_balance"]) - 1.0 + float(rta["R_total"]) + float(rta["T_total"])) > 1.0e-7:
        raise ValueError(f"aggregate balance mismatch: {geometry}/{angle_id}")
    _m0_values(sample)


@dataclass
class ReplayData:
    geometries: np.ndarray
    source_kind: list[str]
    j1: np.ndarray
    j0: np.ndarray
    inventory: list[dict[str, Any]]
    train_count: int
    external_indices: list[int]
    train_indices: list[int]
    train_manifest_sha256: str
    model_lock_sha256: str
    excluded_geometry: tuple[float, float]

    @property
    def responses(self) -> dict[str, np.ndarray]:
        return {"J1": self.j1, "J0": self.j0}


def _provenance_rows(root: Path) -> dict[tuple[int, int], list[dict[str, Any]]]:
    rows = json.loads((root / "provenance.json").read_text())
    output: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        output.setdefault((int(row["geometry_index"]), int(row["angle_index"])), []).append(row)
    return output


def load_replay_data(repo_root: Path) -> ReplayData:
    root = Path(repo_root).resolve()
    train_root = root / TRAIN_ROOT_REL
    manifest_path = train_root / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("status") != "immutable" or manifest.get("geometry_count") != 37:
        raise ValueError("Task006 train37 manifest is not the expected immutable dataset")
    if manifest.get("forward_solver_sha") != FORWARD_SOLVER_SHA or manifest.get("observable_schema_version") != OBSERVABLE_SCHEMA:
        raise ValueError("Task006 train37 identity mismatch")
    train_geometry = np.load(train_root / "geometries.npy")
    train_j1 = np.asarray(np.load(train_root / "s1_selected_powers.npy"), dtype=np.float64).reshape(37, -1)
    train_j0 = np.asarray(np.load(train_root / "aggregates.npy")[:, :, :2], dtype=np.float64).reshape(37, -1)
    angle_ids = json.loads((train_root / "angle_ids.json").read_text())
    if tuple(angle_ids) != tuple(row[0] for row in ANGLES):
        raise ValueError("angle order mismatch in train37")
    provenance = _provenance_rows(train_root)
    inventory: list[dict[str, Any]] = []
    for index, geometry in enumerate(train_geometry.tolist()):
        rows = []
        for angle_index, (angle_id, grazing, azimuth) in enumerate(ANGLES):
            records = provenance.get((index, angle_index), [])
            if len(records) != 1:
                raise ValueError(f"train provenance not unique for row {index}/{angle_id}")
            rows.append(records[0])
        inventory.append({
            "geometry_index": index, "geometry": [float(geometry[0]), float(geometry[1])],
            "source_kind": "task006_train37_immutable_compact_dataset",
            "angle_records": rows,
            "source_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID,
            "solver_route_id": ROUTE_ID, "observable_schema_version": OBSERVABLE_SCHEMA,
            "channel_contract": "J1=S+P order_total_power at reflection/transmission m=0; J0=R_total,T_total",
        })

    external_j1: list[list[float]] = []
    external_j0: list[list[float]] = []
    external_inventory: list[dict[str, Any]] = []
    case_root = root / CASE141_ROOT_REL
    for ext_index, geometry in enumerate(EXTERNAL_GEOMETRIES):
        h, w = geometry
        j1_row: list[float] = []
        j0_row: list[float] = []
        angle_records: list[dict[str, Any]] = []
        for angle_id, grazing, azimuth in ANGLES:
            sample_path = case_root / f"{h:g}_{w:g}" / angle_id / "task006_production_sample.json"
            formal_path = case_root / f"{h:g}_{w:g}" / angle_id / "results/task002_full3d_record.json"
            execution_path = case_root / f"{h:g}_{w:g}" / angle_id / "execution.json"
            sample = _json_sample(sample_path)
            _validate_sample(sample, geometry, angle_id, grazing, azimuth)
            reflection, transmission = _m0_values(sample)
            j1_row.extend([reflection, transmission])
            j0_row.extend([float(sample["aggregates"]["R_total"]), float(sample["aggregates"]["T_total"])])
            angle_records.append({
                "angle_id": angle_id, "grazing_deg": grazing, "azimuth_deg": azimuth,
                "sample_path": str(sample_path), "formal_record_path": str(formal_path),
                "execution_path": str(execution_path),
                "sample_sha256": sha256_file(sample_path),
                "formal_record_sha256": sha256_file(formal_path),
                "execution_sha256": sha256_file(execution_path),
                "sample_id": sample.get("sample_id"), "point_hash": sample.get("point_hash"),
                "design_index": sample.get("design_index"),
                "source_sha": sample.get("source_sha"), "model_id": sample.get("model_id"),
                "solver_route_id": sample.get("solver_route_id"),
                "observable_schema_version": sample.get("observable_schema_version"),
                "numerical_gates": sample.get("numerical_gates"),
            })
        external_j1.append(j1_row); external_j0.append(j0_row)
        external_inventory.append({
            "geometry_index": 37 + ext_index, "geometry": [h, w],
            "source_kind": "case141_external_replay_target",
            "angle_records": angle_records, "source_sha": FORWARD_SOLVER_SHA,
            "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
            "observable_schema_version": OBSERVABLE_SCHEMA,
            "qualification_label": "external_replay_target_not_task006_blind_pass",
        })

    geometries = np.vstack((train_geometry, np.asarray(EXTERNAL_GEOMETRIES, dtype=np.float64)))
    return ReplayData(
        geometries=geometries,
        source_kind=["train37"] * 37 + ["external_replay_target"] * len(EXTERNAL_GEOMETRIES),
        j1=np.vstack((train_j1, np.asarray(external_j1, dtype=np.float64))),
        j0=np.vstack((train_j0, np.asarray(external_j0, dtype=np.float64))),
        inventory=inventory + external_inventory,
        train_count=37, train_indices=list(range(37)),
        external_indices=list(range(37, 37 + len(EXTERNAL_GEOMETRIES))),
        train_manifest_sha256=sha256_file(manifest_path),
        model_lock_sha256=sha256_file(root / LOCK_REL),
        excluded_geometry=EXCLUDED_GEOMETRY,
    )


def initial_sets(geometry: np.ndarray, size: int, count: int = 6) -> list[np.ndarray]:
    """Deterministic maximin subsets; all seeds are fixed and train-only."""
    values = np.asarray(geometry, dtype=np.float64)
    scaled = scale_geometry(values)
    output: list[np.ndarray] = []
    for set_id in range(count):
        selected = [int((set_id * 7) % len(values))]
        while len(selected) < size:
            remaining = [index for index in range(len(values)) if index not in selected]
            distances = np.min(np.linalg.norm(scaled[remaining, None, :] - scaled[selected][None, :, :], axis=2), axis=1)
            best_distance = float(np.max(distances))
            candidates = [index for index, distance in zip(remaining, distances)
                          if abs(float(distance) - best_distance) <= 1.0e-14]
            selected.append(min(candidates))
        output.append(np.asarray(selected, dtype=np.int64))
    return output


class ObjectiveGP:
    """Exact Matern-5/2 ARD GP with training-only jitter selection."""

    def __init__(self, seed: int):
        self.seed = int(seed)
        self.model: ExactARDGP | None = None
        self.selected_jitter: float | None = None
        self.candidates: list[dict[str, Any]] = []

    def fit(self, x: np.ndarray, y: np.ndarray) -> "ObjectiveGP":
        self.candidates = []
        for jitter in (1.0e-10, 1.0e-8):
            model = ExactARDGP(jitter=jitter, optimizer_restarts=8,
                               random_state=self.seed, normalize_y=True).fit(x, y)
            self.candidates.append({"jitter": jitter, "metadata": model.metadata()})
            if self.model is None or model.log_marginal_likelihood_ > self.model.log_marginal_likelihood_:
                self.model = model; self.selected_jitter = jitter
        return self

    def predict(self, x: np.ndarray, *, return_std: bool = False):
        if self.model is None:
            raise RuntimeError("objective GP is not fitted")
        return self.model.predict(x, return_std=return_std)

    def metadata(self) -> dict[str, Any]:
        selected = self.model.metadata() if self.model is not None else None
        return {
            "kernel": "Matern-5/2-ARD", "mean": "constant", "normalize_y": True,
            "optimizer_starts": 8, "jitter_candidates": [1.0e-10, 1.0e-8],
            "selected_jitter": self.selected_jitter,
            "selected": selected, "jitter_candidates_metadata": self.candidates,
        }


def expected_improvement(mu: np.ndarray, std: np.ndarray, best: float) -> np.ndarray:
    """Stable EI for minimization of log objective."""
    from scipy.special import ndtr

    mean = np.asarray(mu, dtype=np.float64)
    sigma = np.asarray(std, dtype=np.float64)
    out = np.zeros_like(mean)
    active = sigma > 1.0e-14
    z = np.zeros_like(mean)
    z[active] = (float(best) - mean[active]) / sigma[active]
    out[active] = (float(best) - mean[active]) * ndtr(z[active]) + sigma[active] * np.exp(-0.5 * z[active] ** 2) / np.sqrt(2.0 * np.pi)
    return np.maximum(out, 0.0)


def choose_ei(gp: ObjectiveGP, geometry: np.ndarray, available: Iterable[int], best: float) -> tuple[int, dict[str, Any]]:
    indices = np.asarray(sorted(int(index) for index in available), dtype=np.int64)
    if len(indices) == 0:
        raise ValueError("no acquisition candidates remain")
    mean, std = gp.predict(scale_geometry(geometry[indices]), return_std=True)
    ei = expected_improvement(mean, std, best)
    chosen_position = int(np.argmax(ei))
    chosen = int(indices[chosen_position])
    return chosen, {"candidate_indices": indices.tolist(), "mean": mean.tolist(),
                    "std": std.tolist(), "expected_improvement": ei.tolist(),
                    "chosen_index": chosen, "chosen_ei": float(ei[chosen_position])}


def continuous_map(gp: ObjectiveGP, *, grid_size: int = 101, starts: int = 8) -> dict[str, Any]:
    axis = np.linspace(-1.0, 1.0, grid_size)
    grid = np.asarray([(h, w) for h in axis for w in axis], dtype=np.float64)
    mean = np.asarray(gp.predict(grid), dtype=np.float64)
    order = np.argsort(mean, kind="mergesort")[:starts]
    runs: list[dict[str, Any]] = []
    best = None
    for index in order:
        result = minimize(lambda point: float(gp.predict(np.asarray(point)[None, :])[0]),
                          grid[int(index)], method="L-BFGS-B", bounds=[(-1.0, 1.0), (-1.0, 1.0)],
                          options={"maxiter": 300, "ftol": 1.0e-14, "gtol": 1.0e-10})
        row = {"start": grid[int(index)].tolist(), "x": np.asarray(result.x).tolist(),
               "fun": float(result.fun), "success": bool(result.success),
               "status": int(result.status), "message": str(result.message),
               "nit": int(result.nit)}
        runs.append(row)
        if best is None or row["fun"] < best["fun"]:
            best = row
    if best is None:
        raise RuntimeError("continuous map had no optimizer runs")
    point_scaled = np.asarray(best["x"], dtype=np.float64)
    point = DOMAIN_MIN + (point_scaled + 1.0) * 0.5 * (DOMAIN_MAX - DOMAIN_MIN)
    return {"grid_size": grid_size, "grid_min_log10F": float(np.min(mean)),
            "grid_min_scaled": grid[int(order[0])].tolist(), "optimizer_runs": runs,
            "selected_scaled": point_scaled.tolist(), "selected_geometry": point.tolist(),
            "selected_log10F": float(best["fun"]), "all_optimizer_success": all(row["success"] for row in runs)}
