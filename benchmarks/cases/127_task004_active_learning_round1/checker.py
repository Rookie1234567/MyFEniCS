"""Independent, response-blind checker for Required Task004 M4E2.

The checker intentionally does not import ``src.surrogate.angle.m4e2``.  It
reconstructs the F1 coordinates, nearest-support distances, geometric support
classification, tuple identities, OOF row contracts and plan Gates from the
stored coordinates and immutable train96 arrays.  It never opens a blind
response package and it never executes a solver.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay, QhullError
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PACKAGE = REPO / "benchmarks/artifacts/cases/125_task004_angle_training_qualification/train96"
OUTCOMES = REPO / "surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes"
V2 = OUTCOMES / "SUPPORTED_INTERPOLATION_WINDOWS_V2.json"
STRESS = REPO / "benchmarks/cases/125_task004_angle_training_qualification/outcomes/SPATIAL_HOLDOUT_WINDOWS.json"
TRAINING = REPO / "benchmarks/cases/123_task004_nominal_geometry_angle_surrogate/training_design.json"
VALIDATION = REPO / "benchmarks/cases/123_task004_nominal_geometry_angle_surrogate/frozen_validation_design.json"
POOL = REPO / "benchmarks/cases/123_task004_nominal_geometry_angle_surrogate/candidate_pool.json"
V3 = OUTCOMES / "SUPPORTED_INTERPOLATION_WINDOWS_V3.json"
OOF = OUTCOMES / "M4E2_OOF_ERROR_MAP.json"
QUALITY = OUTCOMES / "M4E2_ACQUISITION_QUALITY.json"
PLAN = OUTCOMES / "ACTIVE_LEARNING_ROUND1_PLAN_V2.json"
OUT = ROOT / "records/case127_check.json"

FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
CODE_SHA = "33f7a84b93a99a7cbd92dfb1d7fc9cb2055134e0"
DATASET_ID = "task004_angle_nominal_p5_ny4_train96_v2"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
WINDOW_NAMES = {"low_grazing", "high_azimuth", "cutoff_near", "ordinary_interior"}
TARGETS = ("R_total", "T_total", "A_balance")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def f1(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return np.column_stack((2.0 * (values[:, 0] - 5.25) / 9.5,
                            2.0 * values[:, 1] / 90.0 - 1.0))


def boundary_edges(point: np.ndarray) -> list[str]:
    grazing, azimuth = map(float, point)
    edges = []
    if abs(grazing - 0.5) <= 1.0e-10:
        edges.append("grazing_min")
    if abs(grazing - 10.0) <= 1.0e-10:
        edges.append("grazing_max")
    if abs(azimuth) <= 1.0e-10:
        edges.append("azimuth_min")
    if abs(azimuth - 90.0) <= 1.0e-10:
        edges.append("azimuth_max")
    return edges


def classify_support(query: np.ndarray, support: np.ndarray) -> dict[str, object]:
    """Independent counterpart of the V3 support contract."""
    qf = f1(query[None, :])[0]
    sf = f1(support)
    vectors = sf - qf[None, :]
    distances = np.linalg.norm(vectors, axis=1)
    sectors = np.unique(np.floor((np.arctan2(vectors[:, 1], vectors[:, 0]) + np.pi) /
                                 (np.pi / 4.0)).astype(int))
    contains = False
    hull_error = None
    if len(sf) >= 3 and np.linalg.matrix_rank(sf - sf[0]) >= 2:
        try:
            contains = bool(Delaunay(sf).find_simplex(qf) >= 0)
        except QhullError as exc:
            hull_error = str(exc)
    edges = boundary_edges(query)
    inward_counts: dict[str, int] = {}
    tangent_spans: dict[str, float] = {}
    for edge in edges:
        if edge == "grazing_min":
            inward, tangent = support[:, 0] - query[0], support[:, 1] - query[1]
        elif edge == "grazing_max":
            inward, tangent = query[0] - support[:, 0], support[:, 1] - query[1]
        elif edge == "azimuth_min":
            inward, tangent = support[:, 1] - query[1], support[:, 0] - query[0]
        else:
            inward, tangent = query[1] - support[:, 1], support[:, 0] - query[0]
        inward_counts[edge] = int(np.sum(inward > 1.0e-8))
        tangent_spans[edge] = float(np.ptp(tangent))
    boundary_supported = bool(edges and all(
        inward_counts[e] >= 2 and tangent_spans[e] >= 0.02 for e in edges
    ))
    if edges and boundary_supported:
        label = "boundary_one_sided_supported"
    elif contains and len(sectors) >= 3:
        label = "interior_bracketed"
    else:
        label = "unsupported_extrapolation"
    return {
        "classification": label,
        "convex_hull_contains": contains,
        "hull_error": hull_error,
        "direction_sector_count": int(len(sectors)),
        "direction_sectors": sectors.astype(int).tolist(),
        "boundary_edges": edges,
        "inward_support_counts": inward_counts,
        "tangent_spans": tangent_spans,
        "local_rank": int(np.linalg.matrix_rank(vectors)) if len(vectors) else 0,
        "nearest_support_distance": float(np.min(distances)) if len(distances) else float("inf"),
    }


def tuple_rows(path: Path) -> list[list[float]]:
    data = json.loads(path.read_text())
    return [[float(np.round(float(point[key]), 12)) for key in
             ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]
            for point in data["points"]]


def quality_row(signal: np.ndarray, error: np.ndarray) -> dict[str, float | int]:
    count = max(1, int(np.ceil(len(signal) * 0.20)))
    high_signal = set(np.argsort(signal, kind="mergesort")[-count:])
    high_error = set(np.argsort(error, kind="mergesort")[-count:])
    top10 = set(np.argsort(error, kind="mergesort")[-10:])
    rho = 0.0 if np.ptp(signal) == 0 or np.ptp(error) == 0 else float(
        spearmanr(signal, error).statistic
    )
    if not np.isfinite(rho):
        rho = 0.0
    return {"spearman": rho,
            "top20_error_recall": float(len(high_signal & high_error) / len(high_error)),
            "top10_error_covered_by_top20_acquisition": int(len(top10 & high_signal)),
            "top20_count": int(count)}


def points_in_angle_order(candidate: dict, angles: np.ndarray) -> dict[tuple[float, float], dict]:
    rows = {}
    for row in candidate.get("points", []):
        angle = tuple(float(v) for v in row["angle"])
        rows[angle] = row
    expected = {tuple(float(v) for v in row) for row in np.asarray(angles).round(12)}
    if set(rows) != expected:
        raise ValueError("OOF point angles do not exactly cover train96")
    return rows


def main() -> int:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    required = [PACKAGE / "dataset_manifest.json", PACKAGE / "file_hashes.json",
                PACKAGE / "angles.npy", PACKAGE / "inputs.npy", PACKAGE / "aggregates.npy",
                V2, V3, OOF, QUALITY, PLAN, STRESS, TRAINING, VALIDATION, POOL]
    checks["required_artifacts_present"] = all(path.is_file() for path in required)
    if not checks["required_artifacts_present"]:
        errors.append("a required M4E2 or immutable train96 artifact is missing")
        return write_result(checks, errors)

    manifest = json.loads((PACKAGE / "dataset_manifest.json").read_text())
    stored = json.loads((PACKAGE / "file_hashes.json").read_text())
    actual = {path.name: digest(path) for path in sorted(PACKAGE.iterdir())
              if path.is_file() and path.name != "file_hashes.json"}
    angles = np.load(PACKAGE / "angles.npy", allow_pickle=False)
    inputs = np.load(PACKAGE / "inputs.npy", allow_pickle=False)
    checks["train96_hashes_rebuild"] = actual == stored
    checks["train96_identity"] = bool(
        manifest.get("dataset_id") == DATASET_ID and manifest.get("sample_count") == 96 and
        manifest.get("training_count") == 96 and manifest.get("forward_solver_sha") == FORWARD_SHA and
        manifest.get("validation_target_accessed") is False and manifest.get("immutable") is True and
        np.all(inputs[:, :2] == np.asarray([120.0, 17.0])) and angles.shape == (96, 2)
    )
    train_tuples = tuple_rows(TRAINING)
    checks["training_tuple_identity"] = bool(
        json.loads(TRAINING.read_text()).get("point_count") == 96 and
        manifest.get("training_tuple_sha256") == canonical(train_tuples) and
        inputs.round(12).tolist() == train_tuples
    )

    v2 = json.loads(V2.read_text()); v3 = json.loads(V3.read_text())
    checks["v3_identity_and_authorities"] = bool(
        v3.get("schema_version") == "task004.supported-interpolation-windows.v3" and
        v3.get("dataset_id") == DATASET_ID and
        v3.get("training_tuple_sha256") == manifest.get("training_tuple_sha256") and
        v3.get("surrogate_training_code_sha") == CODE_SHA and
        v3.get("v2_authority", {}).get("sha256") == digest(V2) and
        v3.get("stress_authority", {}).get("sha256") == digest(STRESS) and
        v3.get("stress_authority", {}).get("status") == "advisory_extrapolation_stress" and
        json.loads(STRESS.read_text()).get("schema_version") == "task004.spatial-holdout-windows.v1"
    )
    support_ok = True
    for item in v3.get("windows", []):
        if item.get("name") not in WINDOW_NAMES:
            support_ok = False
            continue
        holdout = np.asarray(item.get("indices", []), dtype=np.int64)
        support_rows = item.get("support_rows", [])
        support_indices = np.asarray(item.get("support_indices", []), dtype=np.int64)
        if len(holdout) != len(support_rows) or support_indices.shape != (len(holdout), 6):
            support_ok = False
            continue
        for row, index in zip(support_rows, holdout):
            support = np.asarray(row["support_coordinates"], dtype=np.float64)
            if not np.array_equal(np.asarray(row["support_indices"], dtype=np.int64),
                                  support_indices[int(np.where(holdout == index)[0][0])]):
                support_ok = False
            recomputed = classify_support(angles[index], support)
            for key in ("classification", "convex_hull_contains", "direction_sector_count",
                        "direction_sectors", "boundary_edges", "inward_support_counts",
                        "local_rank"):
                if row.get(key) != recomputed.get(key):
                    support_ok = False
            expected_distance = float(np.linalg.norm(
                f1(support)[0] - f1(angles[index][None, :])[0]
            ))
            if not np.isclose(row.get("nearest_support_distance"), expected_distance, atol=1e-12):
                support_ok = False
            if not np.allclose(np.asarray(row.get("support_feature_coordinates")), f1(support)):
                support_ok = False
    checks["v3_geometry_support_recomputed"] = bool(
        support_ok and len(v3.get("windows", [])) == 4 and
        {item.get("name") for item in v3.get("windows", [])} == WINDOW_NAMES and
        v3.get("classification_contract", {}).get("checker_recomputes_from_coordinates") is True
    )

    oof = json.loads(OOF.read_text())
    expected_candidates = {
        "L1_local_rbf_k24_s1e-08", "L2_local_matern_k24", "L2_local_matern_k32",
        "L4_trend_local_residual_k32", "L2_local_matern_f4_k24", "L2_local_matern_f4_k32",
    }
    point_fields = {"angle", "truth", "prediction", "error", "absolute_error",
                    "predictive_std", "inner_conformal_radius", "fold",
                    "nearest_fold_training_distance", "cutoff_order",
                    "signed_cutoff_margin", "mask_signature", "region_labels",
                    "neighbor_indices", "conformal_radius", "standardized_residual"}
    oof_ok = bool(oof.get("schema_version") == "task004.m4e2.oof-error-map.v1" and
                  oof.get("dataset_id") == DATASET_ID and
                  oof.get("surrogate_training_code_sha") == CODE_SHA and
                  oof.get("validation_target_accessed") is False and
                  set(oof.get("candidates", {})) == expected_candidates)
    candidate_rows: dict[str, dict[tuple[float, float], dict]] = {}
    for name, candidate in oof.get("candidates", {}).items():
        try:
            rows = points_in_angle_order(candidate, angles)
        except (ValueError, TypeError):
            oof_ok = False
            continue
        candidate_rows[name] = rows
        if len(candidate.get("points", [])) != 96:
            oof_ok = False
        for row in candidate.get("points", []):
            if not point_fields.issubset(row):
                oof_ok = False
            if not np.all(np.isfinite(np.asarray(row.get("truth"), dtype=float))):
                oof_ok = False
            if not np.all(np.isfinite(np.asarray(row.get("prediction"), dtype=float))):
                oof_ok = False
            if not np.allclose(np.asarray(row["error"]),
                               np.asarray(row["prediction"]) - np.asarray(row["truth"]),
                               atol=1e-12):
                oof_ok = False
    checks["oof_error_maps_complete"] = oof_ok
    checks["finite_f1_f4_matern_comparison"] = bool(
        all(name in candidate_rows for name in (
            "L2_local_matern_k24", "L2_local_matern_k32",
            "L2_local_matern_f4_k24", "L2_local_matern_f4_k32"))
    )

    quality = json.loads(QUALITY.read_text())
    checks["acquisition_identity_and_gate"] = bool(
        quality.get("schema_version") == "task004.m4e2.acquisition-quality.v1" and
        quality.get("surrogate_training_code_sha") == CODE_SHA and
        quality.get("gate") is True and quality.get("ensemble_non_antirelated") is True and
        abs(sum(float(v) for v in quality.get("weights", {}).values()) - 1.0) <= 1e-12
    )
    audit_ok = True
    if "L2_local_matern_k24" in candidate_rows:
        def values(name: str, field: str) -> np.ndarray:
            return np.asarray([candidate_rows[name][tuple(row.round(12))][field]
                               for row in angles], dtype=float)
        truth = np.asarray([candidate_rows["L2_local_matern_k24"][tuple(row.round(12))]["truth"]
                            for row in angles], dtype=float)
        pred24 = np.asarray([candidate_rows["L2_local_matern_k24"][tuple(row.round(12))]["prediction"]
                             for row in angles], dtype=float)
        pred32 = np.asarray([candidate_rows["L2_local_matern_k32"][tuple(row.round(12))]["prediction"]
                             for row in angles], dtype=float)
        pred_rbf = np.asarray([candidate_rows["L1_local_rbf_k24_s1e-08"][tuple(row.round(12))]["prediction"]
                               for row in angles], dtype=float)
        errors24 = np.abs(pred24 - truth)
        signals = {
            "native_std_k24": np.asarray([candidate_rows["L2_local_matern_k24"][tuple(row.round(12))]["native_std"]
                                           for row in angles], dtype=float),
            "native_std_k32": np.asarray([candidate_rows["L2_local_matern_k32"][tuple(row.round(12))]["native_std"]
                                           for row in angles], dtype=float),
            "matern_k24_k32_disagreement": np.abs(pred24 - pred32),
            "rbf_matern_disagreement": np.abs(pred_rbf - pred24),
            "nearest_training_distance": np.asarray([candidate_rows["L2_local_matern_k24"][tuple(row.round(12))]["nearest_fold_training_distance"]
                                                      for row in angles], dtype=float)[:, None],
        }
        for name, signal in signals.items():
            for channel in range(3):
                expected = quality.get("signal_reports", {}).get(name, [])[channel]
                got = quality_row(signal[:, channel] if signal.shape[1] > 1 else signal[:, 0],
                                  errors24[:, channel])
                if any(abs(float(got[key]) - float(expected.get(key))) > 1e-12
                       for key in got):
                    audit_ok = False
    checks["acquisition_spearman_and_recall_recomputed"] = audit_ok

    pool_data = json.loads(POOL.read_text()); validation_tuples = tuple_rows(VALIDATION)
    plan = json.loads(PLAN.read_text())
    pool_tuples = tuple_rows(POOL)
    train_set = {tuple(row) for row in train_tuples}
    validation_set = {tuple(row) for row in validation_tuples}
    pool_set = {tuple(row) for row in pool_tuples}
    plan_rows = plan.get("points", [])
    plan_tuples = [tuple(float(v) for v in row.get("tuple", [])) for row in plan_rows]
    plan_set = set(plan_tuples)
    plan_ok = bool(
        plan.get("schema_version") == "task004.active-learning-round1-plan.v2" and
        plan.get("surrogate_training_code_sha") == CODE_SHA and
        plan.get("forward_solver_sha") == FORWARD_SHA and
        plan.get("model_identity", {}).get("model_id") == MODEL_ID and
        plan.get("model_identity", {}).get("solver_route_id") == ROUTE_ID and
        plan.get("model_identity", {}).get("mesh") == [6, 4, 14] and
        plan.get("model_identity", {}).get("mumps_icntl_14") == 40 and
        plan.get("model_identity", {}).get("mpi") == 2 and
        plan.get("model_identity", {}).get("threads_per_rank") == 1 and
        len(plan_rows) == 16 and plan.get("candidate_pool_count") == 4096 and
        plan.get("training_tuple_sha256") == manifest.get("training_tuple_sha256") and
        plan.get("candidate_pool_tuple_sha256") == pool_data.get("point_tuple_sha256") and
        plan.get("validation_tuple_sha256") == json.loads(VALIDATION.read_text()).get("point_tuple_sha256") and
        plan.get("point_tuple_sha256") == canonical([list(row) for row in plan_tuples])
    )
    reasons = [set(row.get("selection_reasons", [])) for row in plan_rows]
    counts = {
        "hotspot": sum("matern_error_or_disagreement_hotspot" in r for r in reasons),
        "high_azimuth": sum("high_azimuth_difficulty" in r for r in reasons),
        "low_or_cutoff": sum("low_grazing_or_cutoff_side" in r for r in reasons),
        "ordinary_interior": sum("ordinary_interior_hole" in r for r in reasons),
        "rare_unseen_topology": sum(bool(row.get("rare_unseen_topology")) for row in plan_rows),
    }
    fplan = f1(np.asarray([row[2:] for row in train_tuples], dtype=float))
    fpool = f1(np.asarray([list(t)[2:] for t in plan_set], dtype=float)) if plan_set else np.empty((0, 2))
    pairwise = [float(np.linalg.norm(fpool[i] - fpool[j]))
                for i in range(len(fpool)) for j in range(i + 1, len(fpool))]
    train_signatures = {str(row.get("mask_signature")) for row in
                        [candidate_rows["L2_local_matern_k24"][tuple(a.round(12))]
                         for a in angles]} if candidate_rows else set()
    plan_ok = bool(plan_ok and plan_set.issubset(pool_set) and plan_set.isdisjoint(train_set | validation_set) and
                   len(plan_set) == 16 and counts == plan.get("category_counts") and
                   counts["hotspot"] >= 6 and counts["high_azimuth"] >= 3 and
                   counts["low_or_cutoff"] >= 3 and counts["ordinary_interior"] >= 3 and
                   counts["rare_unseen_topology"] >= 2 and pairwise and min(pairwise) >= 0.035 and
                   plan.get("status") == "ready_for_m4f" and plan.get("fem_authorized_if_gates_pass") is True and
                   plan.get("response_blind") is True and plan.get("validation_response_accessed") is False)
    checks["exact_16_plan_independently_checked"] = plan_ok

    checks["no_blind_or_fem_access"] = bool(
        manifest.get("validation_target_accessed") is False and
        not (PACKAGE / "sealed_validation_indices.npy").exists() and
        not any((ROOT / "records").glob("fem*"))
    )
    checks["all_checks"] = bool(all(checks.values()) and not errors)
    return write_result(checks, errors, plan=plan, quality=quality)


def write_result(checks: dict[str, bool], errors: list[str], *, plan: dict | None = None,
                 quality: dict | None = None) -> int:
    result = {"schema_version": "case127.check.v1",
              "status": "pass" if checks.get("all_checks", False) else "fail",
              "checks": checks, "errors": errors, "point_count": len((plan or {}).get("points", [])),
              "plan_status": (plan or {}).get("status"),
              "acquisition_gate": (quality or {}).get("gate"),
              "validation_response_accessed": False, "fem_started": False}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
