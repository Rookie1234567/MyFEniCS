from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import resource
import time
from typing import Any, Mapping

import numpy as np
from mpi4py import MPI


ROOT = Path(__file__).resolve().parents[2]
CASE093 = ROOT / "benchmarks/cases/093_fixed_geometry_ph_convergence_mpi"
CASE092 = ROOT / "benchmarks/cases/092_workstation_wsl_adaptive_scalability"

_SAMPLE_PATHS = {
    "p2_h5": "p2_h5_full-solve_mpi8_20260719T011823Z",
    "p2_h3": "p2_h3_full-solve_mpi8_20260719T022046Z",
    "p2_h2": "p2_h2_full-solve_mpi8_20260719T030543Z",
    "p3_h10": "p3_h10_full-solve_mpi8_20260719T063149Z",
    "p3_h7p5": "p3_h7.5_full-solve_mpi8_20260719T063508Z",
    "p4_h5": "p4_h5_full-solve_mpi8_20260719T093000Z",
}
_DEGREE_H = {
    "p2_h5": (2, 5.0),
    "p2_h3": (2, 3.0),
    "p2_h2": (2, 2.0),
    "p3_h10": (3, 10.0),
    "p3_h7p5": (3, 7.5),
    "p4_h5": (4, 5.0),
}
_SCREEN_PAIRS = (
    ("p2_h5", "p2_h3"),
    ("p2_h3", "p2_h2"),
    ("p3_h10", "p3_h7p5"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sample_path(key: str) -> Path:
    return (
        ROOT
        / "benchmarks/artifacts/task034/phase_f/full3d"
        / _SAMPLE_PATHS[key]
        / "full3d_reference_samples.npz"
    )


def _load_sample(key: str) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    path = _sample_path(key)
    descriptor_path = path.with_suffix(".json")
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    actual_sha = _sha256(path)
    if actual_sha != descriptor["archive_sha256"]:
        raise RuntimeError(f"Task034 sample hash mismatch for {key}")
    with np.load(path) as archive:
        arrays = {name: np.asarray(archive[name]) for name in archive.files}
    return arrays, {
        "archive": str(path.relative_to(ROOT)),
        "archive_sha256": actual_sha,
        "descriptor": str(descriptor_path.relative_to(ROOT)),
        "descriptor_sha256": _sha256(descriptor_path),
        "source_shape": descriptor["array_shape_z_y_x_component"],
    }


def _curl(field: np.ndarray, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    edge_order = 2
    d_dx = np.gradient(field, x, axis=2, edge_order=edge_order)
    d_dy = np.gradient(field, y, axis=1, edge_order=edge_order)
    d_dz = np.gradient(field, z, axis=0, edge_order=edge_order)
    result = np.empty_like(field)
    result[..., 0] = d_dy[..., 2] - d_dz[..., 1]
    result[..., 1] = d_dz[..., 0] - d_dx[..., 2]
    result[..., 2] = d_dx[..., 1] - d_dy[..., 0]
    return result


def _epsilon_grid(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    x = arrays["x_nm"][None, None, :]
    z = arrays["z_nm"][:, None, None]
    n_material = 0.999002304859 + 0.00182649365j
    inside_grating = (x >= 16.5) & (x <= 33.5) & (z >= 0.0) & (z <= 120.0)
    shape = arrays["E_V_per_m"].shape[:-1]
    return np.broadcast_to(np.where(inside_grating, n_material**2, 1.0), shape)


def _r1_sampled_residual(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    """Sampled strong Maxwell residual; this is not a cell-integrated FE R1."""

    electric = arrays["E_V_per_m"]
    scaled_magnetic = 376.730313668 * arrays["H_A_per_m"]
    x = arrays["x_nm"]
    y = arrays["y_nm"]
    z = arrays["z_nm"]
    k0 = 2.0 * math.pi / 13.5
    faraday = _curl(electric, x, y, z) - 1j * k0 * scaled_magnetic
    ampere = _curl(scaled_magnetic, x, y, z) + 1j * k0 * (
        _epsilon_grid(arrays)[..., None] * electric
    )
    return np.sqrt(np.sum(np.abs(faraday) ** 2 + np.abs(ampere) ** 2, axis=-1))


def _field_difference(
    left: Mapping[str, np.ndarray], right: Mapping[str, np.ndarray]
) -> np.ndarray:
    electric = left["E_V_per_m"] - right["E_V_per_m"]
    magnetic = 376.730313668 * (left["H_A_per_m"] - right["H_A_per_m"])
    return np.sqrt(np.sum(np.abs(electric) ** 2 + np.abs(magnetic) ** 2, axis=-1))


def _rankdata(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    return ranks


def _correlations(indicator: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    left = indicator.ravel().astype(float)
    right = actual.ravel().astype(float)
    pearson = float(np.corrcoef(left, right)[0, 1])
    spearman = float(np.corrcoef(_rankdata(left), _rankdata(right))[0, 1])
    return {"pearson": pearson, "spearman": spearman}


def _marked(values: np.ndarray, theta: float = 0.5) -> np.ndarray:
    flat = np.square(values.ravel().astype(float))
    order = np.argsort(-flat, kind="mergesort")
    cutoff = theta * float(np.sum(flat))
    count = int(np.searchsorted(np.cumsum(flat[order]), cutoff, side="left") + 1)
    return np.sort(order[:count].astype(np.int64))


def _marked_summary(values: np.ndarray) -> dict[str, Any]:
    marked = _marked(values)
    payload = marked.astype("<i8", copy=False).tobytes()
    return {
        "theta": 0.5,
        "count": int(len(marked)),
        "fraction": float(len(marked) / values.size),
        "global_sample_ids_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _overlap(left: np.ndarray, right: np.ndarray) -> float:
    a = set(map(int, _marked(left)))
    b = set(map(int, _marked(right)))
    return len(a & b) / max(1, len(a | b))


def _observable_error(point: Mapping[str, Any], reference: Mapping[str, Any]) -> float:
    names = ("R_total", "T_total", "A_volume_total")
    values = point["full3d"]["official_values"]
    target = reference["full3d"]["official_values"]
    return math.sqrt(
        sum((float(values[name]) - float(target[name])) ** 2 for name in names)
    )


def _dtn_boundary_split(arrays: Mapping[str, np.ndarray]) -> dict[str, float]:
    residual = _r1_sampled_residual(arrays)
    return {
        "bottom_sample_plane_l2": float(np.linalg.norm(residual[0])),
        "top_sample_plane_l2": float(np.linalg.norm(residual[-1])),
        "interior_sample_planes_l2": float(np.linalg.norm(residual[1:-1])),
    }


def _strip_negative_control() -> dict[str, Any]:
    path = CASE092 / "records/adaptive_summary.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    baseline = record["baseline"]
    refined = record["profiles"]["conservative"]["shards"][-1]
    names = ("R_delta_full3d", "T_delta_full3d", "A_volume_delta_full3d")
    before = math.sqrt(sum(float(baseline[name]) ** 2 for name in names))
    after = math.sqrt(sum(float(refined[name]) ** 2 for name in names))
    return {
        "status": "controlled_negative",
        "actual_pde_run": True,
        "estimator_marked_refinement": False,
        "reason": "Task034 strip/tensor refinement was geometry-driven, not a Task035 marked set",
        "observable_error_before": before,
        "observable_error_after": after,
        "observable_error_reduction_fraction": 1.0 - after / before,
        "physical_gates_pass_after": refined["all_reported_physical_gates_pass"],
        "failed_gates": refined["failed_gate_names"],
        "evidence": str(path.relative_to(ROOT)),
        "evidence_sha256": _sha256(path),
    }


def run_target_artifact_bakeoff() -> dict[str, Any]:
    started = time.perf_counter()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    convergence_path = CASE093 / "records/convergence_summary.json"
    convergence = json.loads(convergence_path.read_text(encoding="utf-8"))
    points = {point["key"]: point for point in convergence["points"]}
    arrays: dict[str, dict[str, np.ndarray]] = {}
    bindings: dict[str, Any] = {}
    for key in _SAMPLE_PATHS:
        arrays[key], bindings[key] = _load_sample(key)
    reference = arrays["p4_h5"]
    rows = []
    for coarse_key, enriched_key in _SCREEN_PAIRS:
        coarse = arrays[coarse_key]
        enriched = arrays[enriched_key]
        r1 = _r1_sampled_residual(coarse)
        r5 = _field_difference(coarse, enriched)
        actual = _field_difference(coarse, reference)
        degree, h_nm = _DEGREE_H[coarse_key]
        before = _observable_error(points[coarse_key], points["p4_h5"])
        after = _observable_error(points[enriched_key], points["p4_h5"])
        rows.append(
            {
                "point": coarse_key,
                "enriched_point": enriched_key,
                "target_identity": {
                    "wavelength_nm": 13.5,
                    "incidence_theta_deg": 80.0,
                    "grazing_angle_deg": 10.0,
                    "polarization": "S",
                    "geometry": "Task034 fixed rectangular block grating",
                },
                "R1_sampled_strong_residual_proxy": {
                    "norm": float(np.linalg.norm(r1)),
                    "local_error_correlation": _correlations(r1, actual),
                    "marked_set": _marked_summary(r1),
                },
                "R5_discrete_two_level_proxy": {
                    "norm": float(np.linalg.norm(r5)),
                    "effectivity_proxy": float(
                        np.linalg.norm(r5) / max(np.linalg.norm(actual), 1.0e-30)
                    ),
                    "local_error_correlation": _correlations(r5, actual),
                    "marked_set": _marked_summary(r5),
                    "formal_hierarchical_FE_R5": False,
                },
                "R1_R5_marked_set_jaccard": _overlap(r1, r5),
                "external_DtN_sample_split": _dtn_boundary_split(coarse),
                "R2_kh_over_p": {
                    "value": 2.0 * math.pi * h_nm / (13.5 * degree),
                    "policy": "diagnostic_only_excluded_from_marking",
                },
                "observable_error": {
                    "reference": "accepted Task034 p4/h5 best-available discrete reference",
                    "before": before,
                    "after_enriched": after,
                    "reduction_fraction": 1.0 - after / before,
                    "positive_reduction": after < before,
                },
            }
        )
    rank = MPI.COMM_WORLD.rank
    size = MPI.COMM_WORLD.size
    global_ids = np.arange(np.prod(reference["E_V_per_m"].shape[:-1]), dtype=np.int64)
    local_ids = global_ids[global_ids % size == rank]
    local_identity = np.asarray(
        [len(local_ids), np.sum(local_ids), np.sum(local_ids * local_ids)],
        dtype=np.int64,
    )
    distributed_identity = np.zeros(3, dtype=np.int64)
    MPI.COMM_WORLD.Allreduce(local_identity, distributed_identity, op=MPI.SUM)
    elapsed = time.perf_counter() - started
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    strip = _strip_negative_control()
    all_positive = all(row["observable_error"]["positive_reduction"] for row in rows)
    return {
        "schema_version": "task035.target-artifact-estimator-bakeoff.v1",
        "status": "controlled_negative_provisional_R1",
        "phase_c_internal_gate": "complete_controlled_negative",
        "phase_d_low_cost_unlocked": True,
        "production_estimator_selected": False,
        "reason": "sampled R1/R5 proxies rank target artifacts, but no formal hierarchical FE R5 or estimator-marked target refinement is available",
        "target_artifact_screen_pass": all_positive,
        "mpi_size": size,
        "mpi_partition_identity": {
            "count_sum_sumsq": distributed_identity.tolist(),
            "partition": "global_sample_id_mod_mpi_size",
            "full_field_gather": False,
        },
        "estimator_cost": {
            "wall_seconds": elapsed,
            "process_peak_rss_kib_before": int(rss_before),
            "process_peak_rss_kib_after": int(rss_after),
        },
        "points": rows,
        "actual_refinement_evidence": strip,
        "B3": "pending_parallel_fixture",
        "B4": "pending_parallel_fixture",
        "artifact_bindings": bindings,
        "convergence_record": {
            "path": str(convergence_path.relative_to(ROOT)),
            "sha256": _sha256(convergence_path),
            "physical_identity_sha256": convergence["physical_identity_sha256"],
        },
    }
