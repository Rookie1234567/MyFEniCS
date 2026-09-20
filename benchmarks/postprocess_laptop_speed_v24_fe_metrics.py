"""Offline same-discrete FE metric comparison for the saved V24/V23 fields.

This postprocess reconstructs only the frozen degree-6 mesh, space, and Floquet
MPC, then applies the existing unweighted mass and scaled-curl diagnostics to
the two saved complete vectors.  It does not build a physical operator, factor
anything, or start a PDE solve.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

import numpy as np


QUADRATURE = (
    {"quadrature_degree": 15, "quadrature_rule": "default"},
    {"quadrature_degree": 15, "quadrature_rule": "default"},
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def git_facts(root: Path) -> dict[str, Any]:
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"head": None, "status": None, "error": str(exc)}
    return {"head": head, "status": status.splitlines()}


def full_solution_facts(run_root: Path, summary_name: str) -> tuple[np.ndarray, dict[str, Any]]:
    summary = read_json(run_root / summary_name)
    packet = summary["x2_retained_final"]
    archive = Path(packet["arrays"]["path"])
    if not archive.is_absolute():
        archive = run_root / archive
    if sha256(archive) != packet["arrays"]["sha256"]:
        raise ValueError(f"complete-field archive hash mismatch: {archive}")
    with np.load(archive, allow_pickle=False) as arrays:
        field = np.asarray(arrays[packet["full_solution"]["array_key"]]).copy()
    expected_shape = list(packet["full_solution"]["shape"])
    if list(field.shape) != expected_shape or str(field.dtype) != packet["full_solution"]["dtype"]:
        raise ValueError(f"complete-field descriptor mismatch: {archive}")
    if not np.isfinite(field).all():
        raise ValueError(f"complete field is not finite: {archive}")
    return field, {
        "summary_path": str(run_root / summary_name),
        "summary_sha256": sha256(run_root / summary_name),
        "archive_path": str(archive),
        "archive_sha256": sha256(archive),
        "array_key": packet["full_solution"]["array_key"],
        "shape": list(field.shape),
        "dtype": str(field.dtype),
        "vector_sha256": hashlib.sha256(field.tobytes()).hexdigest(),
        "source_sha": summary.get("source_sha"),
        "input_sha256": summary["operator_identity"].get("input_sha256"),
        "physical_model_sha256": summary["operator_identity"].get("physical_model_sha256"),
        "p6_native_map_sha256": summary["operator_identity"].get("p6_native_map_sha256"),
        "p4_native_map_sha256": summary["operator_identity"].get("p4_native_map_sha256"),
        "quadrature": summary["operator_identity"].get("quadrature"),
        "p6_dimension": summary["actual_dimension_identity"]["p6"],
        "geometry_semantic_identity": summary["actual_dimension_identity"][
            "geometry_semantic_identity"
        ],
        "geometry_audit": summary["geometry_audit"],
    }


def compare_fields(current: Path, old: Path, output: Path, root: Path) -> dict[str, Any]:
    from mpi4py import MPI

    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.physical_error_diagnostics import metric_square
    from src.solvers.physical_error_metric import LosslessFEMetric

    current_field, current_facts = full_solution_facts(
        current, "physical_dual_condensed_laptop_speed_v24_summary.json"
    )
    old_field, old_facts = full_solution_facts(
        old, "physical_dual_condensed_physical_memory_v23_summary.json"
    )
    if current_field.shape != old_field.shape:
        raise ValueError("V24/V23 complete-field shapes differ")
    if current_facts["p6_native_map_sha256"] != old_facts["p6_native_map_sha256"]:
        raise ValueError("V24/V23 p6 native map identity differs")
    if current_facts["p4_native_map_sha256"] != old_facts["p4_native_map_sha256"]:
        raise ValueError("V24/V23 p4 native map identity differs")
    if current_facts["physical_model_sha256"] != old_facts["physical_model_sha256"]:
        raise ValueError("V24/V23 physical model identity differs")
    if current_facts["p6_dimension"] != old_facts["p6_dimension"]:
        raise ValueError("V24/V23 p6 dimension identity differs")
    if current_facts["geometry_semantic_identity"] != old_facts["geometry_semantic_identity"]:
        raise ValueError("V24/V23 geometry semantic identity differs")
    current_quadrature = current_facts["quadrature"]
    old_quadrature = old_facts["quadrature"]
    if current_quadrature != old_quadrature or current_quadrature != list(QUADRATURE):
        raise ValueError("V24/V23 quadrature identity is not the bound degree-15/default pair")

    resolved = read_json(current / "resolved_config.json")
    cfg = simulation_config_3d_from_normalized(resolved)
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=False
    )
    try:
        index_facts = native_map_arrays(
            levels["spaces"][6], levels["floquets"][6]
        )
        from src.runners.physical_macro_controls import _mapping_identity_sha256

        indices = np.asarray(index_facts["independent_indices"], dtype=np.int64)
        p6_map_sha256 = _mapping_identity_sha256(index_facts)
        expected_p6 = "54647a99c97786af88364d6e3f8c6c1d3c7893bbf79afc2888a63cf47be6c06e"
        p6_dimension = current_facts["p6_dimension"]
        mesh = levels["mesh"]
        mesh_cell_count = int(mesh.topology.index_map(mesh.topology.dim).size_global)
        space = levels["spaces"][6]
        space_global_size = int(space.dofmap.index_map.size_global)
        slave_count = int(np.asarray(index_facts["slaves"]).size)
        independent_count = int(indices.size)
        geometry = np.asarray(mesh.geometry.x)
        axis_vertex_counts = [
            int(np.unique(np.round(geometry[:, axis], decimals=12)).size)
            for axis in range(3)
        ]
        axis_cell_counts = [count - 1 for count in axis_vertex_counts]
        geometry_payload = current_facts["geometry_semantic_identity"]["geometry_entity_payload"]
        expected_bounds = [
            [0.0, float(geometry_payload["period_x_nm"])],
            [0.0, float(geometry_payload["period_y_nm"])],
            [float(geometry_payload["z_min_nm"]), float(geometry_payload["z_max_nm"])],
        ]
        actual_bounds = [
            [float(np.min(geometry[:, axis])), float(np.max(geometry[:, axis]))]
            for axis in range(3)
        ]
        identity_checks = {
            "p6_native_map_sha256": p6_map_sha256 == expected_p6,
            "p6_native_map_matches_both_packets": p6_map_sha256
            == current_facts["p6_native_map_sha256"]
            == old_facts["p6_native_map_sha256"],
            "mesh_cells_990": mesh_cell_count == 990,
            "p6_space_global_size_667152": space_global_size == 667152,
            "p6_complete_field_size": current_field.size == 667152,
            "p6_independent_count": independent_count == 667152 - 22392,
            "p6_slave_count_22392": slave_count == 22392,
            "p6_dimension_packet": p6_dimension["full_rows"] == 667152
            and p6_dimension["active_rows"] == 199260
            and p6_dimension["interior_rows"] == 445500
            and p6_dimension["appended_rows"] == 80
            and p6_dimension["slave_rows"] == 22392
            and p6_dimension["owned_cell_count"] == 990,
            "axis_cell_counts_9_5_22": axis_cell_counts == [9, 5, 22]
            and axis_cell_counts == current_facts["geometry_semantic_identity"]["axis_cell_counts"],
            "geometry_bounds": all(
                np.isclose(actual, expected, rtol=0.0, atol=1.0e-12)
                for actual_pair, expected_pair in zip(actual_bounds, expected_bounds)
                for actual, expected in zip(actual_pair, expected_pair)
            ),
            "geometry_audit_owned_cells": current_facts["geometry_audit"]["owned_cell_count"] == 990,
        }
        if not all(identity_checks.values()):
            raise ValueError(f"frozen V21 mesh/DoF/MPC identity failed: {identity_checks}")
        metric = LosslessFEMetric(
            levels,
            6,
            cfg.k0,
            tuple(current_quadrature),
            build_cell_basis=False,
        )
        try:
            current_independent = current_field[indices]
            old_independent = old_field[indices]
            difference = current_independent - old_independent
            metrics: dict[str, Any] = {}
            for name, action in (("L2", metric.mass), ("scaled_curl", metric.curl)):
                error_squared = metric_square(action, difference)
                reference_squared = metric_square(action, old_independent)
                current_squared = metric_square(action, current_independent)
                error_norm = float(np.sqrt(error_squared))
                reference_norm = float(np.sqrt(reference_squared))
                metrics[name] = {
                    "absolute_error_norm": error_norm,
                    "reference_norm": reference_norm,
                    "relative": error_norm / max(reference_norm, np.finfo(float).tiny),
                    "current_norm": float(np.sqrt(current_squared)),
                    "limit": 1.0e-4,
                }
            result = {
                "schema": "task039extra.v24.same-discrete-fe-metrics.v1",
                "execution": {
                    "status": "OFFLINE_METRIC_ONLY",
                    "pde_started": False,
                    "physical_operator_built": False,
                    "factor_started": False,
                    "ksp_started": False,
                    "mpi_size": int(MPI.COMM_WORLD.size),
                },
                "source": {
                    "checker_script": str(Path(__file__).resolve()),
                    "checker_script_sha256": sha256(Path(__file__).resolve()),
                    "repository": git_facts(root),
                },
                "current": current_facts,
                "reference": old_facts,
                "frozen_identity": {
                    "resolved_config_path": str(current / "resolved_config.json"),
                    "resolved_config_sha256": sha256(current / "resolved_config.json"),
                    "p6_native_map_sha256": current_facts["p6_native_map_sha256"],
                    "p4_native_map_sha256": current_facts["p4_native_map_sha256"],
                    "independent_index_count": int(indices.size),
                    "independent_indices_sha256": hashlib.sha256(indices.tobytes()).hexdigest(),
                    "space_global_size": int(levels["spaces"][6].dofmap.index_map.size_global),
                    "axis_vertex_counts": axis_vertex_counts,
                    "axis_cell_counts": axis_cell_counts,
                    "actual_geometry_bounds": actual_bounds,
                    "expected_geometry_bounds": expected_bounds,
                    "p6_native_map_sha256_recomputed": p6_map_sha256,
                    "identity_checks": identity_checks,
                    "quadrature": current_quadrature,
                    "metric_audit": metric.audit,
                },
                "comparison": {
                    "phase_fitting": False,
                    "coordinate_alignment": "complete p6 vector through frozen native map",
                    "vector_difference_norm_euclidean": float(np.linalg.norm(difference)),
                    "metrics": metrics,
                    "max_relative": max(item["relative"] for item in metrics.values()),
                    "limit": 1.0e-4,
                    "pass": all(item["relative"] <= 1.0e-4 for item in metrics.values()),
                },
                "cleanup": {"status": "METRIC_COMPLETE_BEFORE_CLEANUP"},
            }
            atomic_write_json(output, result)
        finally:
            metric.destroy()
            del metric
    finally:
        levels.clear()
    result["cleanup"] = {
        "status": "COMPLETED",
        "metric_destroyed": True,
        "mpc_destroy": "NOT_APPLICABLE_BORROWED_DOLFINX_MPC_LIFETIME",
    }
    atomic_write_json(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current_root", type=Path)
    parser.add_argument("old_root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = compare_fields(
        args.current_root.resolve(), args.old_root.resolve(), args.output.resolve(), args.root.resolve()
    )
    print(json.dumps({"pass": result["comparison"]["pass"], "output": str(args.output)}))
    return 0 if result["comparison"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
