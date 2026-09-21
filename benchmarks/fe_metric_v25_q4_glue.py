"""Minimal supervised, offline Q4/V24 evidence audit.

This file is a tracked, offline-only audit utility.  It compares already-written packets and
rebuilds only the frozen p6 mesh/metric objects; it never assembles an
operator, factors a matrix, or starts a PDE solve.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import resource
import subprocess
import sys
import time
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np


FIELD_LIMIT = 1.0e-4
OUTPUT_LIMIT = 1.0e-5
MODE_POWER_LIMIT = 1.0e-6
MODE_AMPLITUDE_LIMIT = 1.0e-4
TRUE_RESIDUAL_LIMIT = 1.0e-6

V25_SUMMARY = "physical_dual_condensed_coarse_degree_v25_summary.json"
V24_SUMMARY = "physical_dual_condensed_laptop_speed_v24_summary.json"
P6_MAP_SHA = "54647a99c97786af88364d6e3f8c6c1d3c7893bbf79afc2888a63cf47be6c06e"

STAGE_SPECS = {
    "Q4": {"stage": "Q4_ORIGINAL", "prefix": "v25q4", "stem": "q4"},
    "Q3": {"stage": "Q3_ORIGINAL", "prefix": "v25q3", "stem": "q3"},
    "Q2": {"stage": "Q2_ORIGINAL", "prefix": "v25q2", "stem": "q2"},
}
V24_ARTIFACTS = [
    "resolved_config.json", "input_original.dat", "physical_model_sha256.txt",
    "source_sha.txt", "run_manifest.json", "x2_retained_final.json", "x2_retained_final.npz",
    "numerical_output/full3d_reference_samples.json", "numerical_output/full3d_reference_samples.npz",
    "numerical_output/dtn_port_diffraction_orders_3d.json", "numerical_output/volume_absorption.json",
    "official_output/z3_output.json", "official_output/z3_output.npz",
    "final_residual/z3_final.json", "final_residual/z3_final.npz",
    "post_release_final_residual/z3_post_release_final.json", "post_release_final_residual/z3_post_release_final.npz",
    "v24_ordered_mode_manifest.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def complex_value(value: Any) -> complex:
    if isinstance(value, Mapping):
        return complex(float(value["real"]), float(value["imag"]))
    if isinstance(value, (list, tuple)):
        return complex(float(value[0]), float(value[1]))
    return complex(value)


def rel_norm(delta: np.ndarray, reference: np.ndarray) -> float:
    return float(np.linalg.norm(delta.ravel()) /
                 max(float(np.linalg.norm(reference.ravel())), np.finfo(float).tiny))


def full_solution_facts(run_root: Path, summary_name: str) -> tuple[np.ndarray, dict[str, Any]]:
    from benchmarks.postprocess_laptop_speed_v24_fe_metrics import full_solution_facts as helper

    return helper(run_root, summary_name)


def artifact_hashes(run_root: Path, relative_paths: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for relative in relative_paths:
        path = run_root / relative
        if not path.is_file():
            result[relative] = {"exists": False}
            continue
        result[relative] = {"exists": True, "sha256": sha256(path), "bytes": path.stat().st_size}
    return result


def config_bridge(current: Path, reference: Path) -> dict[str, Any]:
    current_cfg = read_json(current / "resolved_config.json")
    reference_cfg = read_json(reference / "resolved_config.json")
    sections = ("geometry", "materials", "incidence", "boundary", "dimension")
    discretization_keys = (
        "assembly_backend", "floquet_constraint_mode", "mesh_axis_cell_counts",
        "mesh_axis_x_values", "mesh_axis_y_values", "mesh_axis_z_profile",
        "mesh_axis_z_values", "mesh_cell_type", "mesh_plan_id", "mesh_plan_sha256",
        "mesh_spacing_mode", "mesh_target_nm", "nedelec_degree", "visualization_degree",
    )
    current_projection = {
        **{name: current_cfg[name] for name in sections},
        "discretization": {name: current_cfg["discretization"][name]
                           for name in discretization_keys},
    }
    reference_projection = {
        **{name: reference_cfg[name] for name in sections},
        "discretization": {name: reference_cfg["discretization"][name]
                           for name in discretization_keys},
    }
    equality = current_projection == reference_projection
    return {
        "selected_sections": list(sections) + ["discretization"],
        "discretization_keys": list(discretization_keys),
        "current_projection_sha256": canonical_sha(current_projection),
        "reference_projection_sha256": canonical_sha(reference_projection),
        "semantic_projection_equal": equality,
        "current_input_sha256": sha256(current / "input_original.dat"),
        "reference_input_sha256": sha256(reference / "input_original.dat"),
        "current_physical_model_sha256": read_json(current / "physical_dual_condensed_coarse_degree_v25_summary.json")["operator_identity"]["physical_model_sha256"],
        "reference_physical_model_sha256": read_json(reference / "physical_dual_condensed_laptop_speed_v24_summary.json")["operator_identity"]["physical_model_sha256"],
        "current": current_projection,
        "reference": reference_projection,
    }


def residual_facts(run_root: Path, relative: str) -> dict[str, Any]:
    from benchmarks.check_laptop_speed_v24 import residual_packet_facts

    return residual_packet_facts(run_root / relative, run_root)


def residual_audit(current: Path, reference: Path, spec: Mapping[str, str]) -> dict[str, Any]:
    current_final = residual_facts(current, f"final_residual/{spec['stem']}_final.json")
    current_post = residual_facts(current, f"post_release_final_residual/{spec['stem']}_post_release_final.json")
    reference_final = residual_facts(reference, "final_residual/z3_final.json")
    return {
        "current_final": current_final,
        "current_post_release": current_post,
        "reference_final": reference_final,
        "gate": bool(
            current_final["checks"]["gate"]
            and current_post["checks"]["gate"]
            and current_final["checks"]["residual_matches_rhs_minus_applied"]
            and current_post["checks"]["residual_matches_rhs_minus_applied"]
        ),
    }


def mesh_and_fe_metrics(current: Path, reference: Path,
                        current_field: np.ndarray, reference_field: np.ndarray,
                        current_facts: Mapping[str, Any],
                        reference_facts: Mapping[str, Any]) -> dict[str, Any]:
    from mpi4py import MPI
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.runners.physical_macro_controls import _mapping_identity_sha256
    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.physical_error_diagnostics import metric_square
    from src.solvers.physical_error_metric import LosslessFEMetric

    cfg = simulation_config_3d_from_normalized(read_json(current / "resolved_config.json"))
    levels = _build_same_mesh_levels(cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=False)
    metric = None
    try:
        index_facts = native_map_arrays(levels["spaces"][6], levels["floquets"][6])
        indices = np.asarray(index_facts["independent_indices"], dtype=np.int64)
        slaves = np.asarray(index_facts["slaves"], dtype=np.int64)
        p6_map_sha = _mapping_identity_sha256(index_facts)
        mesh = levels["mesh"]
        geometry = np.asarray(mesh.geometry.x)
        axis_vertex_counts = [int(np.unique(np.round(geometry[:, axis], decimals=12)).size)
                              for axis in range(3)]
        axis_cell_counts = [count - 1 for count in axis_vertex_counts]
        actual_bounds = [[float(np.min(geometry[:, axis])), float(np.max(geometry[:, axis]))]
                         for axis in range(3)]
        cfg_geometry = read_json(current / "resolved_config.json")["geometry"]
        expected_bounds = [
            [0.0, float(cfg_geometry["period_x_nm"])],
            [0.0, float(cfg_geometry["period_y_nm"])],
            [float(cfg_geometry["z_min_nm"]), float(cfg_geometry["z_max_nm"])],
        ]
        p6_checks = {
            "recomputed_map_matches_bound": p6_map_sha == P6_MAP_SHA,
            "recomputed_map_matches_current_packet": p6_map_sha == current_facts["p6_native_map_sha256"],
            "recomputed_map_matches_reference_packet": p6_map_sha == reference_facts["p6_native_map_sha256"],
            "mesh_cells_990": int(mesh.topology.index_map(mesh.topology.dim).size_global) == 990,
            "p6_space_global_size_667152": int(levels["spaces"][6].dofmap.index_map.size_global) == 667152,
            "p6_complete_field_size": current_field.size == reference_field.size == 667152,
            "p6_independent_count_644760": indices.size == 644760,
            "p6_slave_count_22392": int(np.asarray(index_facts["slaves"]).size) == 22392,
            "current_slave_slots_strict_zero": bool(np.count_nonzero(current_field[slaves]) == 0),
            "reference_slave_slots_strict_zero": bool(np.count_nonzero(reference_field[slaves]) == 0),
            "axis_cell_counts_9_5_22": axis_cell_counts == [9, 5, 22],
            "geometry_bounds": all(
                math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-12)
                for actual_pair, expected_pair in zip(actual_bounds, expected_bounds)
                for actual, expected in zip(actual_pair, expected_pair)
            ),
        }
        packet_keys = ("full_rows", "active_rows", "interior_rows", "appended_rows", "slave_rows", "owned_cell_count")
        current_p6 = current_facts["p6_dimension"]
        reference_p6 = reference_facts["p6_dimension"]
        p6_checks.update({
            "current_p6_packet_expected": current_p6["full_rows"] == 667152 and current_p6["active_rows"] == 199260 and current_p6["interior_rows"] == 445500 and current_p6["appended_rows"] == 80 and current_p6["slave_rows"] == 22392 and current_p6["owned_cell_count"] == 990,
            "reference_p6_packet_expected": reference_p6["full_rows"] == 667152 and reference_p6["active_rows"] == 199260 and reference_p6["interior_rows"] == 445500 and reference_p6["appended_rows"] == 80 and reference_p6["slave_rows"] == 22392 and reference_p6["owned_cell_count"] == 990,
            "p6_packets_equal": all(current_p6[key] == reference_p6[key] for key in packet_keys),
            "quadrature_bound": current_facts["quadrature"] == reference_facts["quadrature"] == [{"quadrature_degree": 15, "quadrature_rule": "default"}, {"quadrature_degree": 15, "quadrature_rule": "default"}],
        })
        metric = LosslessFEMetric(levels, 6, cfg.k0, tuple(current_facts["quadrature"]), build_cell_basis=False)
        current_independent = current_field[indices]
        reference_independent = reference_field[indices]
        difference = current_independent - reference_independent
        metrics: dict[str, Any] = {}
        for name, action in (("L2", metric.mass), ("scaled_curl", metric.curl)):
            error_norm = float(np.sqrt(metric_square(action, difference)))
            reference_norm = float(np.sqrt(metric_square(action, reference_independent)))
            metrics[name] = {
                "absolute_error_norm": error_norm,
                "reference_norm": reference_norm,
                "relative": error_norm / max(reference_norm, np.finfo(float).tiny),
                "limit": FIELD_LIMIT,
            }
        return {
            "execution": {"status": "OFFLINE_METRIC_ONLY", "pde_started": False,
                          "physical_operator_built": False, "factor_started": False,
                          "ksp_started": False, "mpi_size": int(MPI.COMM_WORLD.size)},
            "identity": {
                "recomputed_p6_native_map_sha256": p6_map_sha,
                "independent_index_count": int(indices.size),
                "independent_indices_sha256": hashlib.sha256(indices.tobytes()).hexdigest(),
                "space_global_size": int(levels["spaces"][6].dofmap.index_map.size_global),
                "axis_vertex_counts": axis_vertex_counts,
                "axis_cell_counts": axis_cell_counts,
                "actual_geometry_bounds": actual_bounds,
                "expected_geometry_bounds": expected_bounds,
                "checks": p6_checks,
            },
            "comparison": {"phase_fitting": False, "metrics": metrics,
                           "max_relative": max(item["relative"] for item in metrics.values()),
                           "limit": FIELD_LIMIT,
                           "pass": all(item["relative"] <= FIELD_LIMIT for item in metrics.values())},
        }
    finally:
        if metric is not None:
            metric.destroy()
        levels.clear()


def sample_audit(current: Path, reference: Path) -> dict[str, Any]:
    names = ("x_nm", "y_nm", "z_nm", "interface_z_nm")
    values = ("E_V_per_m", "H_A_per_m", "E_t_interface_V_per_m", "H_t_interface_A_per_m")
    current_path = current / "numerical_output/full3d_reference_samples.npz"
    reference_path = reference / "numerical_output/full3d_reference_samples.npz"
    result: dict[str, Any] = {"current_archive_sha256": sha256(current_path),
                              "reference_archive_sha256": sha256(reference_path),
                              "coordinates": {}, "values": {}}
    with np.load(current_path, allow_pickle=False) as left_archive, np.load(reference_path, allow_pickle=False) as right_archive:
        coordinate_gate = True
        for name in names:
            left, right = np.asarray(left_archive[name]), np.asarray(right_archive[name])
            exact = bool(left.shape == right.shape and np.array_equal(left, right))
            coordinate_gate = coordinate_gate and exact
            result["coordinates"][name] = {"shape": list(left.shape), "exact": exact}
        for name in values:
            left, right = np.asarray(left_archive[name]), np.asarray(right_archive[name])
            if left.shape != right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
                raise ValueError(f"sample shape/finite mismatch: {name}")
            absolute = float(np.max(np.abs(left - right), initial=0.0))
            reference_norm = float(np.linalg.norm(right.ravel()))
            relative = rel_norm(left - right, right)
            near_zero = reference_norm <= 1.0e-12 and absolute <= 1.0e-10
            result["values"][name] = {"shape": list(left.shape), "relative_l2": relative,
                                      "max_absolute": absolute, "reference_norm": reference_norm,
                                      "near_zero_absolute_gate": near_zero,
                                      "pass": bool(relative <= FIELD_LIMIT or near_zero)}
    result["coordinate_gate"] = coordinate_gate
    result["pass"] = bool(coordinate_gate and all(item["pass"] for item in result["values"].values()))
    return result


def official_vector_audit(current: Path, reference: Path, spec: Mapping[str, str]) -> dict[str, Any]:
    current_packet = read_json(current / f"official_output/{spec['stem']}_output.json")
    reference_packet = read_json(reference / "official_output/z3_output.json")

    def load(packet: Mapping[str, Any]) -> tuple[np.ndarray, str]:
        archive = Path(packet["arrays"]["path"])
        if sha256(archive) != packet["arrays"]["sha256"]:
            raise ValueError(f"official output archive hash mismatch: {archive}")
        with np.load(archive, allow_pickle=False) as arrays:
            vector = np.asarray(arrays["array_0"]).copy()
        if vector.shape != (80,) or vector.dtype != np.dtype("complex128") or not np.isfinite(vector).all():
            raise ValueError(f"official vector descriptor mismatch: {archive}")
        return vector, sha256(archive)

    current_vector, current_archive_sha = load(current_packet)
    reference_vector, reference_archive_sha = load(reference_packet)
    delta = current_vector - reference_vector
    relative = rel_norm(delta, reference_vector)
    stage_ok = current_packet.get("identity", {}).get("stage") == spec["stage"]
    return {"current_archive_sha256": current_archive_sha,
            "reference_archive_sha256": reference_archive_sha,
            "shape": list(current_vector.shape), "dtype": str(current_vector.dtype),
            "relative_l2": relative, "max_absolute": float(np.max(np.abs(delta))),
            "limit": MODE_AMPLITUDE_LIMIT, "stage_identity": stage_ok,
            "pass": bool(stage_ok and relative <= MODE_AMPLITUDE_LIMIT)}


def modes_and_outputs(current: Path, reference: Path, spec: Mapping[str, str]) -> dict[str, Any]:
    from src.runners.physical_balanced_output import compare_modal_files, compare_power_totals
    from src.runners.physical_macro_v12 import _compare_saved_output
    from benchmarks.check_dual_condensed_robustness_v21 import (
        _check_channels,
        _field_output_facts_v21,
    )

    current_orders = read_json(current / "numerical_output/dtn_port_diffraction_orders_3d.json")["orders"]
    reference_orders = read_json(reference / "numerical_output/dtn_port_diffraction_orders_3d.json")["orders"]

    def key(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
        return str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"])

    current_keys = [key(row) for row in current_orders]
    reference_keys = [key(row) for row in reference_orders]
    current_by_key = {key(row): row for row in current_orders}
    reference_by_key = {key(row): row for row in reference_orders}
    same_keys = (current_keys == reference_keys and len(current_keys) == 80
                 and len(set(current_keys)) == 80 and len(set(reference_keys)) == 80)
    power_differences = {
        field: max((abs(float(current_by_key[k][field]) - float(reference_by_key[k][field]))
                    for k in current_by_key), default=math.inf)
        for field in ("R", "T", "power_ratio", "modal_power_code_units")
    }
    current_output = read_json(current / f"official_output/{spec['stem']}_output.json")["output"]
    reference_output = read_json(reference / "official_output/z3_output.json")["output"]
    totals = compare_power_totals(current_output, reference_output)
    modal = compare_modal_files(current / "numerical_output", reference / "numerical_output")
    saved_output = _compare_saved_output(
        current_output, reference_output,
        current_dir=current / "numerical_output",
        reference_dir=reference / "numerical_output",
    )
    channel_checks, channel_facts = _check_channels(current / "numerical_output", current_output)
    field_checks, field_facts = _field_output_facts_v21(current / "numerical_output", current_output)
    closure = saved_output["closure"]
    closure_checks = {
        name: finite(value) and abs(float(value)) <= OUTPUT_LIMIT
        for name, value in closure.items()
    }
    finite_checks = saved_output["finite"]
    selected_field = saved_output["selected_field"]
    saved_output_gate = bool(
        all(bool(value) for value in finite_checks.values())
        and all(closure_checks.values())
        and selected_field.get("status") == "AVAILABLE"
        and all(bool(item.get("pass")) for item in selected_field.get("differences", {}).values())
    )
    channel_gate = all(channel_checks.values())
    field_gate = all(field_checks.values())
    total_gate = max(totals["total_absolute_differences"].values()) <= OUTPUT_LIMIT
    modal_gate = (same_keys and power_differences["R"] <= MODE_POWER_LIMIT
                  and power_differences["T"] <= MODE_POWER_LIMIT
                  and power_differences["power_ratio"] <= MODE_POWER_LIMIT)
    return {
        "mode_inventory": {"current_count": len(current_orders), "reference_count": len(reference_orders),
                           "same_ordered_80_keys": same_keys, "phase_fitting": False},
        "per_mode_power": {"max_absolute_differences": power_differences,
                           "limit": MODE_POWER_LIMIT, "pass": modal_gate},
        "saved_modal_checker": modal,
        "saved_output_checks": {
            "finite": finite_checks,
            "closure": closure,
            "closure_checks": closure_checks,
            "selected_field": selected_field,
            "pass": saved_output_gate,
        },
        "channel_checks_v21": {"checks": channel_checks, "facts": channel_facts, "pass": channel_gate},
        "field_checks_v21": {"checks": field_checks, "facts": field_facts, "pass": field_gate},
        "RTA_A_volume": {**totals, "limit": OUTPUT_LIMIT, "pass": total_gate},
        "pass": bool(modal_gate and total_gate
                      and modal["amplitude_relative_difference"] <= MODE_AMPLITUDE_LIMIT
                      and saved_output_gate and channel_gate and field_gate),
    }


def source_and_hash_audit(current: Path, reference: Path, current_facts: Mapping[str, Any],
                          reference_facts: Mapping[str, Any], spec: Mapping[str, str]) -> dict[str, Any]:
    common = [
        "resolved_config.json", "input_original.dat", "physical_model_sha256.txt",
        "source_sha.txt", "run_manifest.json", "x2_retained_final.json", "x2_retained_final.npz",
        "numerical_output/full3d_reference_samples.json", "numerical_output/full3d_reference_samples.npz",
        "numerical_output/dtn_port_diffraction_orders_3d.json", "numerical_output/volume_absorption.json",
        f"official_output/{spec['stem']}_output.json", f"official_output/{spec['stem']}_output.npz",
        f"final_residual/{spec['stem']}_final.json", f"final_residual/{spec['stem']}_final.npz",
        f"post_release_final_residual/{spec['stem']}_post_release_final.json",
        f"post_release_final_residual/{spec['stem']}_post_release_final.npz",
        f"{spec['prefix']}_ordered_mode_manifest.json",
    ]
    reference_paths = list(V24_ARTIFACTS)
    current_manifest = read_json(current / "run_manifest.json")
    reference_manifest = read_json(reference / "run_manifest.json")
    current_source_file = (current / "source_sha.txt").read_text(encoding="utf-8").strip()
    reference_source_file = (reference / "source_sha.txt").read_text(encoding="utf-8").strip()
    checks = {
        "current_source_consistent": current_source_file == current_facts["source_sha"] == current_manifest.get("source_sha"),
        "reference_source_consistent": reference_source_file == reference_facts["source_sha"] == reference_manifest.get("source_sha"),
        "current_input_hash_matches_packet": sha256(current / "input_original.dat") == current_facts["input_sha256"],
        "reference_input_hash_matches_packet": sha256(reference / "input_original.dat") == reference_facts["input_sha256"],
        "current_physical_hash_record_matches_packet": (current / "physical_model_sha256.txt").read_text(encoding="utf-8").strip() == current_facts["physical_model_sha256"],
        "reference_physical_hash_record_matches_packet": (reference / "physical_model_sha256.txt").read_text(encoding="utf-8").strip() == reference_facts["physical_model_sha256"],
    }
    current_files = artifact_hashes(current, common)
    reference_files = artifact_hashes(reference, reference_paths)
    checks["current_required_artifacts_present"] = all(item.get("exists") for item in current_files.values())
    checks["reference_required_artifacts_present"] = all(item.get("exists") for item in reference_files.values())
    return {"current": {"source_sha": current_source_file, "files": current_files},
            "reference": {"source_sha": reference_source_file, "files": reference_files},
            "checks": checks, "pass": all(checks.values())}


def saved_slave_zero_facts(run_root: Path) -> dict[str, Any]:
    packet_path = run_root / "x2_retained_final.json"
    packet = read_json(packet_path)
    archive = Path(packet["arrays"]["path"])
    if sha256(archive) != packet["arrays"]["sha256"]:
        raise ValueError(f"complete-field archive hash mismatch: {archive}")
    with np.load(archive, allow_pickle=False) as arrays:
        field = np.asarray(arrays[packet["full_solution"]["array_key"]])
        slaves = np.asarray(arrays[packet["owned_slave_rows"]["array_key"]])
    valid = (slaves.dtype == np.dtype("int32") and slaves.size == 22392
             and np.all(slaves >= 0) and np.all(slaves < field.size))
    zero = bool(valid and np.count_nonzero(field[slaves]) == 0)
    return {"packet_sha256": sha256(packet_path), "archive_sha256": sha256(archive),
            "field_shape": list(field.shape), "slave_shape": list(slaves.shape),
            "slave_dtype": str(slaves.dtype), "strict_zero": zero}


def cheap_supplement(current: Path, reference: Path, existing_path: Path,
                     output: Path, stage: str) -> dict[str, Any]:
    spec = STAGE_SPECS[stage]
    existing = read_json(existing_path)
    current_facts = existing["current"]
    reference_facts = existing["reference"]
    hashes = source_and_hash_audit(current, reference, current_facts, reference_facts, spec)
    residual = residual_audit(current, reference, spec)
    outputs = modes_and_outputs(current, reference, spec)
    current_slave = saved_slave_zero_facts(current)
    reference_slave = saved_slave_zero_facts(reference)
    slave_gate = current_slave["strict_zero"] and reference_slave["strict_zero"]
    result = {
        "schema": "task039extra.v25.q4-independent-audit-supplement.v1",
        "status": "PASS" if bool(
            existing.get("status") == "PASS" and hashes["pass"] and residual["gate"]
            and outputs["pass"] and slave_gate
        ) else "FAIL",
        "execution": {"status": "OFFLINE_SAVED_PACKET_ONLY", "pde_started": False,
                      "metric_rebuilt": False, "stage": spec["stage"]},
        "reused_fe": {
            "existing_audit": str(existing_path.resolve()),
            "existing_audit_sha256": sha256(existing_path),
            "existing_tool": existing.get("tool"),
            "existing_fe_metrics": existing.get("fe_metrics"),
            "existing_official_80_mode_vector": existing.get("official_80_mode_vector"),
        },
        "source_and_hashes": hashes,
        "raw_residual": residual,
        "saved_slave_zero": {"current": current_slave, "reference": reference_slave,
                             "pass": slave_gate},
        "mode_and_output_regression": outputs,
    }
    write_json(output, result)
    return result


def audit(current: Path, reference: Path, output: Path, repo_root: Path, stage: str) -> dict[str, Any]:
    spec = STAGE_SPECS[stage]
    started = datetime.now(timezone.utc).isoformat()
    start_monotonic = time.monotonic()
    current_field, current_facts = full_solution_facts(current, V25_SUMMARY)
    reference_field, reference_facts = full_solution_facts(reference, V24_SUMMARY)
    config = config_bridge(current, reference)
    source_hashes = source_and_hash_audit(current, reference, current_facts, reference_facts, spec)
    residual = residual_audit(current, reference, spec)
    fe = mesh_and_fe_metrics(current, reference, current_field, reference_field,
                             current_facts, reference_facts)
    tool_path = Path(__file__).resolve()
    write_json(output / "fe_metrics.json", {
        "schema": "task039extra.v25.early-fe-metrics.v1",
        "stage": spec["stage"],
        "source_sha": current_facts.get("source_sha"),
        "tool": {"path": str(tool_path), "sha256": sha256(tool_path)},
        "current": current_facts,
        "reference": reference_facts,
        "config_bridge": config,
        "fe_metrics": fe,
    })
    samples = sample_audit(current, reference)
    vector = official_vector_audit(current, reference, spec)
    outputs = modes_and_outputs(current, reference, spec)
    result = {
        "schema": f"task039extra.v25.{stage.lower()}-independent-audit.v2",
        "stage": spec["stage"],
        "status": "PASS" if all((config["semantic_projection_equal"], source_hashes["pass"],
                                   residual["gate"], all(fe["identity"]["checks"].values()),
                                   fe["comparison"]["pass"], samples["pass"], vector["pass"], outputs["pass"])) else "FAIL",
        "execution": {"status": "OFFLINE_METRIC_ONLY", "pde_started": False,
                      "factor_started": False, "ksp_started": False,
                      "physical_operator_built": False, "started_utc": started,
                      "ended_utc": None, "elapsed_seconds": None,
                      "worker_pid": os.getpid(),
                      "worker_maxrss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024},
        "tool": {"path": str(tool_path), "sha256": sha256(tool_path),
                 "repo_root": str(repo_root.resolve())},
        "current": current_facts,
        "reference": reference_facts,
        "config_bridge": config,
        "source_and_hashes": source_hashes,
        "raw_residual": residual,
        "fe_metrics": fe,
        "same_coordinate_samples": samples,
        "official_80_mode_vector": vector,
        "mode_and_output_regression": outputs,
    }
    result["execution"]["ended_utc"] = datetime.now(timezone.utc).isoformat()
    result["execution"]["elapsed_seconds"] = time.monotonic() - start_monotonic
    write_json(output / "audit.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-root", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--stage", choices=tuple(STAGE_SPECS), default="Q4")
    parser.add_argument("--supplement-existing", type=Path)
    parser.add_argument("--worker", action="store_true")
    return parser.parse_args()


def supervised(args: argparse.Namespace) -> int:
    from benchmarks.subreaper_watchdog import supervise
    from src.io.physical_intermediate_profile import COARSE_DEGREE_SPEED_PROFILE, profile_facts
    from src.runners.workflow_timebase import CONSERVATIVE_REALTIME

    if args.output.exists():
        raise FileExistsError(f"refusing to reuse existing audit/watchdog directory: {args.output}")
    profile = profile_facts(COARSE_DEGREE_SPEED_PROFILE)
    command = ["/usr/bin/mpiexec", "-n", "1", sys.executable, str(Path(__file__).resolve()),
               "--worker", "--current-root", str(args.current_root.resolve()),
               "--reference-root", str(args.reference_root.resolve()),
               "--output", str(args.output.resolve()), "--repo-root", str(args.repo_root.resolve()),
               "--stage", args.stage]
    started = datetime.now(timezone.utc).isoformat()
    authority = supervise(
        command,
        args.output.resolve(),
        wall_seconds=float(profile["resources"]["workflow_seconds"]),
        grace_seconds=30.0,
        hard_stop_immediate=True,
        phase_path=args.output.resolve() / "workflow_phase.json",
        timebase_guard=True,
        timebase_policy=CONSERVATIVE_REALTIME,
        stop_on_global_swap=True,
        time_policy="observe_only",
        memory_policy=profile["resources"]["watchdog_memory_policy"],
    )
    audit_path = args.output / "audit.json"
    if audit_path.is_file():
        payload = read_json(audit_path)
    else:
        payload = {"schema": "task039extra.v25.q4-independent-audit.v1",
                   "status": "WORKER_FAILED_WITHOUT_AUDIT"}
    payload["wrapper"] = {"started_utc": started,
                          "ended_utc": datetime.now(timezone.utc).isoformat(),
                          "command": command,
                          "watchdog": authority,
                          "watchdog_root": str(args.output.resolve()),
                          "watchdog_maxrss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024}
    write_json(audit_path, payload)
    print(json.dumps({"status": payload.get("status"), "watchdog": authority.get("classification"),
                      "audit": str(audit_path)}, ensure_ascii=False))
    return 0 if authority.get("classification") == "COMPLETED" and payload.get("status") == "PASS" else 1


def main() -> int:
    args = parse_args()
    if args.supplement_existing is not None:
        result = cheap_supplement(
            args.current_root.resolve(), args.reference_root.resolve(),
            args.supplement_existing.resolve(), args.output.resolve(), args.stage,
        )
        print(json.dumps({"status": result["status"], "output": str(args.output.resolve())},
                         ensure_ascii=False))
        return 0 if result["status"] == "PASS" else 1
    if args.worker:
        try:
            result = audit(args.current_root.resolve(), args.reference_root.resolve(),
                           args.output.resolve(), args.repo_root.resolve(), args.stage)
            return 0 if result["status"] == "PASS" else 1
        except Exception as exc:
            args.output.mkdir(parents=True, exist_ok=True)
            write_json(args.output / "audit.json", {
                "schema": "task039extra.v25.q4-independent-audit.v1",
                "status": "ERROR", "error": f"{type(exc).__name__}: {exc}",
            })
            raise
    return supervised(args)


if __name__ == "__main__":
    raise SystemExit(main())
