#!/usr/bin/env python3
"""Recover E2's saved p6 field outputs offline; no factorization or PDE solve."""

from __future__ import annotations

import gc
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping

import numpy as np

ROOT = Path("/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering")

RUN_ROOT = ROOT / (
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_e2_manual_m2_growth_v1__full3d_iterative__mpi1__Mna/"
    "20261002T023827.030745Z"
)
INPUT = ROOT / "input/task40extra_0p7nm_engineering/nonseparable_e2_p6_q4_manual_m2_growth.dat"
REPAIR_ROOT = RUN_ROOT / "postprocess_repair_v1"
OUTPUT = REPAIR_ROOT / "numerical_output"
RECORD = REPAIR_ROOT / "repair_record.json"
LAUNCHER = ROOT / "benchmarks/task40_e2_saved_field_recovery_v1/launch.sh"
SUPERVISOR = ROOT / "benchmarks/task40_e2_saved_field_recovery_v1/supervise.py"

ORIGINAL_SOURCE = "63dd2a7378153f2ab5094eb5e7a98d05758a39bf"
ORIGINAL_INPUT = "955bb5051e0cc466124b7fefe7402cdb7aa49618bc2f3eaa02ee5f11b3e6d09b"
PHYSICAL_MODEL = "48814d5fe34ab0e73de345c2d98661a96ef93ebb9690be738d040edac7cd84a7"
FIELD_ARCHIVE = "dd34f56651b45499bf1680a6e860334a0ab3a206a936cc4954e0538a85bac7cf"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        return jsonable(value.item())
    return value


def load_array(archive: Any, descriptor: Mapping[str, Any]) -> np.ndarray:
    value = np.asarray(archive[str(descriptor["array_key"])])
    if list(value.shape) != list(descriptor["shape"]) or str(value.dtype) != descriptor["dtype"]:
        raise ValueError("saved array differs from its packet descriptor")
    return value.copy()


def jsonl_last(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[-1])


def sha256_array(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).view(np.uint8)).hexdigest()


started = time.perf_counter()
assert os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

assert PETSc.ScalarType is np.complex128 and MPI.COMM_WORLD.size == 1
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
assert branch == "task40extra_0p7nm_engineering"
assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
assert REPAIR_ROOT.is_dir() and (REPAIR_ROOT / "watchdog").is_dir()
assert not OUTPUT.exists() and not RECORD.exists()

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.postprocessing.diffraction_3d import (
    _orders_for_modal_fit,
    _power_orders_for_reporting,
    _validate_sample_counts,
    validate_diffraction_sample_counts,
)
from src.postprocessing.task40_saved_field_h_comparison import restore_p6_total_field
from src.runners.physical_macro_controls import _mapping_identity_sha256
from src.solvers.condensed_fine_reference import native_map_arrays
from src.solvers.fullspace_physical_intermediate_runtime import fine_volume_quadrature_metadata
from src.runners.physical_p4_schur_v14 import _v21_authority_limited_checks
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    build_same_mesh_physical_action,
    destroy_same_mesh_physical_action,
    recover_p0_outputs,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

manifest = read_json(RUN_ROOT / "run_manifest.json")
run_summary_path = RUN_ROOT / "run_summary.json"
run_summary = read_json(run_summary_path)
solver_summary_path = RUN_ROOT / "task40extra_nonseparable_0p7nm_p6q4_summary.json"
solver_summary = read_json(solver_summary_path)
original_watchdog = read_json(RUN_ROOT / "watchdog/summary.json")
old_resolved = read_json(RUN_ROOT / "resolved_config.json")
old_input = RUN_ROOT / "input_original.dat"
assert sha256_file(old_input) == ORIGINAL_INPUT == manifest["input_sha256"]
assert manifest["source_sha"] == ORIGINAL_SOURCE
assert manifest["physical_model_sha256"] == PHYSICAL_MODEL

spec = load_and_resolve(INPUT)
resolved = spec.as_jsonable()
assert spec.input_sha256 == sha256_file(INPUT)
assert spec.physical_model_sha256 == PHYSICAL_MODEL
assert spec.identity["run_id"] == manifest["run_id"]
assert spec.identity["model_id"] == manifest["model_id"]
for section in ("geometry", "materials", "incidence", "discretization", "boundary", "method", "solver"):
    assert old_resolved[section] == resolved[section], section
old_output = dict(old_resolved["output"])
new_output = dict(resolved["output"])
assert old_output["diffraction_sample_count_x"] == 24
assert new_output["diffraction_sample_count_x"] == 25
assert new_output["diffraction_sample_count_y"] == 24
old_output["diffraction_sample_count_x"] = 25
assert old_output == new_output

old_cfg = simulation_config_3d_from_normalized(old_resolved)
old_power_orders = _power_orders_for_reporting(old_cfg)
old_fit_orders, _ = _orders_for_modal_fit(old_cfg, old_power_orders)
try:
    _validate_sample_counts(old_cfg, old_fit_orders)
except ValueError as exc:
    old_sampling_error = str(exc)
else:
    raise ValueError("original 24x24 E2 input unexpectedly passes its diffraction catalog")
assert "got 24 x 24, need at least 25 x 7" in old_sampling_error
cfg = simulation_config_3d_from_normalized(resolved)
assert validate_diffraction_sample_counts(cfg) == (25, 7)

x2 = read_json(RUN_ROOT / "x2_retained_final.json")
assert x2["complete_field_saved"] is True
field_archive = Path(x2["arrays"]["path"])
if not field_archive.is_absolute():
    field_archive = RUN_ROOT / field_archive
assert sha256_file(field_archive) == FIELD_ARCHIVE == x2["arrays"]["sha256"]
storage_desc = x2["facts"]["residuals"]["storage_solution"]
with np.load(field_archive, allow_pickle=False) as z:
    solution = load_array(z, storage_desc)
    full_solution = load_array(z, x2["full_solution"])
    rhs = load_array(z, x2["physical_rhs"])
    slave_rows = load_array(z, x2["owned_slave_rows"]).astype(np.int64, copy=False)
assert np.array_equal(solution, full_solution)
del full_solution
assert solution.dtype == np.complex128 and np.isfinite(solution).all() and np.isfinite(rhs).all()
assert slave_rows.size == 22392 and np.all(solution[slave_rows] == 0.0)

final_packet_path = RUN_ROOT / "final_residual/q4_final.json"
final_packet = read_json(final_packet_path)
final_archive = Path(final_packet["arrays"]["path"])
if not final_archive.is_absolute():
    final_archive = RUN_ROOT / final_archive
assert sha256_file(final_archive) == final_packet["arrays"]["sha256"]
with np.load(final_archive, allow_pickle=False) as z:
    assert np.array_equal(load_array(z, final_packet["solution"]), solution)
    assert np.array_equal(load_array(z, final_packet["rhs"]), rhs)
post_packet_path = RUN_ROOT / "post_release_final_residual/q4_post_release_final.json"
post_packet = read_json(post_packet_path)
post_archive = Path(post_packet["arrays"]["path"])
if not post_archive.is_absolute():
    post_archive = RUN_ROOT / post_archive
assert sha256_file(post_archive) == post_packet["arrays"]["sha256"]
pre_residual = float(final_packet["explicit_relative_residual"])
post_residual = float(post_packet["explicit_relative_residual"])

print(json.dumps({
    "progress": "preflight_complete",
    "recovery_source_sha": head,
    "original_run_id": manifest["run_id"],
    "original_sampling_error": old_sampling_error,
    "corrected_input_sha256": spec.input_sha256,
    "physical_model_sha256": PHYSICAL_MODEL,
    "saved_field_sha256": FIELD_ARCHIVE,
}, sort_keys=True), flush=True)

restored = restore_p6_total_field("E2_saved_total", cfg, solution)
levels = restored.levels
bundle = None
p6_space = None
storage_function = None
solution_vec = None
applied_vec = None
try:
    p6_space = levels["spaces"][6]
    cells = int(levels["mesh"].topology.index_map(3).size_global)
    dofs = int(p6_space.dofmap.index_map.size_global)
    assert (cells, dofs) == (880, 595512)
    map_sha = _mapping_identity_sha256(native_map_arrays(p6_space, levels["floquets"][6]))
    expected_map_sha = x2["identity"]["p6_native_map_sha256"]
    assert map_sha == expected_map_sha
    mode_sha = x2["identity"]["ordered_mode_sha256"]

    quadrature, integral_records = fine_volume_quadrature_metadata(levels, cfg)
    assert json.dumps(jsonable(quadrature), sort_keys=True) == json.dumps(
        jsonable(final_packet["identity"]["quadrature"]), sort_keys=True
    )
    bundle = build_same_mesh_physical_action(
        levels, cfg, 6, jit_options=SAME_MESH_JIT_OPTIONS,
        volume_quadrature_metadata=quadrature,
    )
    assert len(bundle["modes"]) == 700 and bundle["mode_sha256"] == mode_sha

    storage_function = fem.Function(p6_space, name="E2_saved_storage_solution")
    storage_function.x.array[:] = solution
    storage_function.x.scatter_forward()
    solution_vec = storage_function.x.petsc_vec
    applied_vec = solution_vec.duplicate()
    applied_vec.set(0.0)
    bundle["physical_action"].apply(solution_vec, applied_vec)
    applied = np.asarray(applied_vec.array, dtype=np.complex128).copy()
    fresh_residual = float(np.linalg.norm(rhs - applied) / np.linalg.norm(rhs))
    del applied
    assert fresh_residual <= 1.0e-6
    OUTPUT.mkdir(parents=True, exist_ok=False)
    output = recover_p0_outputs(
        bundle, solution_vec, OUTPUT, export_all_port_modes=True,
        jit_options=SAME_MESH_JIT_OPTIONS,
    )
    saved_facts = x2["facts"]
    primary_stop = jsonl_last(RUN_ROOT / "primary_stop.jsonl")
    solver_facts = {
        "status": primary_stop["applied_status"],
        "final_true_residual": float(saved_facts["explicit_true_residual"]),
        "final_evaluation": {
            key: float(saved_facts[key])
            for key in (
                "port_closure_relative",
                "internal_residual_relative",
                "native_identity_relative",
                "schur_port_identity_relative",
            )
        },
    }
    authority_checks, authority_facts = _v21_authority_limited_checks(
        solver_facts, output, post_release_relative=post_residual,
        common={"fine": bundle}, output_dir=OUTPUT,
    )
    authority_passed = bool(authority_checks) and all(authority_checks.values())
finally:
    if applied_vec is not None:
        applied_vec.destroy()
    if bundle is not None:
        destroy_same_mesh_physical_action(bundle)
    bundle = None
    del applied_vec, solution_vec, storage_function, p6_space, restored, levels
    gc.collect()

def hash_tree(directory: Path) -> dict[str, Any]:
    return {
        str(path.relative_to(REPAIR_ROOT)): {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(directory.rglob("*")) if path.is_file()
    }

power = read_json(OUTPUT / "dtn_port_power_metrics_3d.json")
volume = read_json(OUTPUT / "volume_absorption.json")
diffraction = read_json(OUTPUT / "diffraction_orders_3d.json")
orders = read_json(OUTPUT / "dtn_port_diffraction_orders_3d.json")
assert power["power_source"] == "dtn_port_modal_amplitudes"
assert int(power["dtn_port_mode_count"]) == len(orders["orders"]) == 700
assert volume["status"] == "ok"
metrics = diffraction["metrics"]
assert (int(metrics["diffraction_sample_count_x"]), int(metrics["diffraction_sample_count_y"])) == (25, 24)
assert (int(metrics["diffraction_min_sample_count_x_for_fit_orders"]),
        int(metrics["diffraction_min_sample_count_y_for_fit_orders"])) == (25, 7)

old_power = read_json(RUN_ROOT / "numerical_output/dtn_port_power_metrics_3d.json")
old_volume = read_json(RUN_ROOT / "numerical_output/volume_absorption.json")
power_delta = {
    key: abs(float(power[key]) - float(old_power[key]))
    for key in ("R_total", "T_total", "A_balance", "R00_s", "R00_p", "R00_total")
}
volume_delta = abs(float(volume["A_volume_total"]) - float(old_volume["A_volume_total"]))
artifacts = hash_tree(OUTPUT)
assert artifacts

record = {
    "schema": "task40extra.e2.saved-field-postprocess-repair.v1",
    "status": (
        "POSTPROCESS_REPAIR_COMPLETE_ORIGINAL_RUN_FAILED"
        if authority_passed else
        "POSTPROCESS_REPAIR_AUTHORITY_GATE_FAIL_ORIGINAL_RUN_FAILED"
    ),
    "classification": (
        "SAVED_FIELD_OFFLINE_OUTPUT_RECOVERY; ORIGINAL_WORKER_FAILED_PRESERVED"
        if authority_passed else
        "SAVED_FIELD_OUTPUTS_DIAGNOSTIC_ONLY; AUTHORITY_GATE_FAILED"
    ),
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "original_run": {
        "run_id": manifest["run_id"],
        "run_root": str(RUN_ROOT),
        "classification": run_summary.get("result_classification"),
        "exit_status": run_summary.get("exit_status"),
        "worker_error": solver_summary.get("error"),
        "run_summary_sha256": sha256_file(run_summary_path),
        "solver_summary_sha256": sha256_file(solver_summary_path),
        "source_sha": manifest["source_sha"],
        "input_sha256": manifest["input_sha256"],
        "physical_model_sha256": manifest["physical_model_sha256"],
        "watchdog_elapsed_seconds": original_watchdog.get("elapsed_seconds"),
        "watchdog_tree_rss_peak_bytes": original_watchdog.get("sampled_process_tree_rss_peak_bytes"),
        "watchdog_tree_swap_peak_bytes": original_watchdog.get("sampled_process_tree_swap_peak_bytes"),
        "descendants_cleared": original_watchdog.get("descendants_cleared"),
        "saved_primary_stop": jsonl_last(RUN_ROOT / "primary_stop.jsonl"),
        "saved_ksp_phase": jsonl_last(RUN_ROOT / "ksp_solve_phase.jsonl"),
        "pre_release_A6_residual": pre_residual,
        "original_post_release_A6_residual": post_residual,
        "post_release_packet_sha256": sha256_file(post_packet_path),
        "post_release_array_sha256": sha256_file(post_archive),
        "original_sampling_error": old_sampling_error,
    },
    "repair_identity": {
        "recovery_source_branch": branch,
        "recovery_source_sha": head,
        "recovery_source_clean": True,
        "recovery_driver_sha256": sha256_file(Path(__file__).resolve()),
        "recovery_launcher_sha256": sha256_file(LAUNCHER),
        "recovery_supervisor_sha256": sha256_file(SUPERVISOR),
        "supervisor_command": "python -u -m benchmarks.task40_e2_saved_field_recovery_v1.supervise",
        "worker_command": "python -u -m benchmarks.task40_e2_saved_field_recovery_v1.recover",
        "corrected_input_sha256": spec.input_sha256,
        "corrected_physical_model_sha256": spec.physical_model_sha256,
        "only_input_change": "output.diffraction_sample_count_x: 24 -> 25; y remains 24",
        "minimum_catalog_sampling": [25, 7],
        "actual_catalog_sampling": [25, 24],
        "saved_field_archive_sha256": FIELD_ARCHIVE,
        "saved_solution_sha256": sha256_array(solution),
        "saved_rhs_sha256": sha256_array(rhs),
        "p6_native_map_sha256": map_sha,
        "ordered_mode_sha256": mode_sha,
        "p6_cells": cells,
        "p6_global_dofs": dofs,
        "p6_quadrature_metadata": jsonable(quadrature),
        "p6_quadrature_integral_records": jsonable(integral_records),
    },
    "fresh_process_native_recheck": {
        "performed_after_original_worker_exit": True,
        "explicit_A6_relative_residual": fresh_residual,
        "residual_gate": 1.0e-6,
        "passed": fresh_residual <= 1.0e-6,
        "native_action_applications": 1,
        "no_p4_setup": True,
        "no_h6_setup": True,
        "no_global_aij": True,
        "no_factor": True,
        "no_ksp": True,
        "no_pde_solve": True,
    },
    "recovered_official_outputs": {
        "output_dir": str(OUTPUT),
        "output_facts": {key: jsonable(value) for key, value in output.items() if key != "auxiliary"},
        "official_power_source": power["power_source"],
        "R_T_A_volume_absolute_delta_vs_original": power_delta,
        "A_volume_total_absolute_delta_vs_original": volume_delta,
        "dtn_mode_count": int(power["dtn_port_mode_count"]),
        "diffraction_sampling": {
            "actual": [metrics["diffraction_sample_count_x"], metrics["diffraction_sample_count_y"]],
            "minimum": [metrics["diffraction_min_sample_count_x_for_fit_orders"],
                        metrics["diffraction_min_sample_count_y_for_fit_orders"]],
        },
        "artifacts": artifacts,
        "authority_checks": authority_checks,
        "authority_check_failed_keys": [key for key, passed in authority_checks.items() if not passed],
        "authority_check_limits": {
            "saved_A6_and_post_release_A6_relative": 1.0e-6,
            "port_closure_relative": 1.0e-8,
            "internal_residual_relative": 1.0e-10,
            "native_identity_relative": 1.0e-10,
            "schur_port_identity_relative": 1.0e-10,
            "energy_and_absorption_closure": 1.0e-5,
            "modal_power_closure": 1.0e-5,
            "per_mode_outgoing_amplitude_match": 1.0e-12,
        },
        "authority_check_measured_facts": jsonable(authority_facts),
        "authority_limited_gate_passed": authority_passed,
        "original_worker_result_mutated": False,
    },
    "additional_cost": {
        "python_process_elapsed_seconds": time.perf_counter() - started,
        "pde_time_added": False,
        "factor_time_added": False,
        "ksp_time_added": False,
        "process_tree_watchdog": "pending launcher finalization",
    },
    "original_worker_result_mutated": False,
}
RECORD.write_text(json.dumps(jsonable(record), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({
    "progress": "recovery_outputs_complete",
    "record": str(RECORD),
    "fresh_process_A6_relative_residual": fresh_residual,
    "R_total": power["R_total"],
    "T_total": power["T_total"],
    "A_balance": power["A_balance"],
    "A_volume_total": volume["A_volume_total"],
    "artifacts": len(artifacts),
    "authority_limited_gate_passed": authority_passed,
}, sort_keys=True), flush=True)
if not authority_passed:
    raise SystemExit(3)
