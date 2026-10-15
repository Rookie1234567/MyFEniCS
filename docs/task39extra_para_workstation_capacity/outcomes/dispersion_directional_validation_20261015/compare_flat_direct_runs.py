#!/usr/bin/env python3
"""Reproduce the offline Nx2/Nx4/Nx8 flat-direct calibration comparison.

This reads only the three terminal run summaries, resolved configs, port/volume
outputs and the small (33.6 KiB) field-sample archives. It never opens a
resource stream, matrix, factor, checkpoint, full field dump or NPZ outside the
sample archive named in each run's metadata.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parents[3]
RUNS = {
    2: Path(
        "results/dispersion_directional_flat_0p7_p6/"
        "dispersion_0p7nm_flat_p6_q160_nx2_direct_v1__full3d_direct__mpi1__Mna/"
        "20261015T063337.960702Z"
    ),
    4: Path(
        "results/dispersion_directional_flat_0p7_p6/"
        "dispersion_0p7nm_flat_p6_q160_nx4_direct_v1__full3d_direct__mpi1__Mna/"
        "20261015T070250.959057Z"
    ),
    8: Path(
        "results/dispersion_directional_flat_0p7_p6/"
        "dispersion_0p7nm_flat_p6_q160_nx8_direct_v2__full3d_direct__mpi1__Mna/"
        "20261015T081936.462265Z"
    ),
}
SAMPLE_ARRAY_KEYS = (
    "x_nm",
    "y_nm",
    "z_nm",
    "interface_z_nm",
    "E_V_per_m",
    "H_A_per_m",
    "E_t_interface_V_per_m",
    "H_t_interface_A_per_m",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _complex_pair(value: Any) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"expected [real, imag] complex pair, got {value!r}")
    return complex(float(value[0]), float(value[1]))


def complex_vector_metrics(candidate: np.ndarray, reference: np.ndarray) -> dict[str, float | None]:
    """Raw complex comparison; deliberately performs no phase alignment."""
    left = np.asarray(candidate, dtype=np.complex128).ravel()
    right = np.asarray(reference, dtype=np.complex128).ravel()
    if left.shape != right.shape:
        raise ValueError(f"complex vector shape mismatch: {left.shape} != {right.shape}")
    delta = left - right
    error_l2 = float(np.linalg.norm(delta))
    reference_l2 = float(np.linalg.norm(right))
    reference_peak = float(np.max(np.abs(right))) if right.size else 0.0
    maximum = float(np.max(np.abs(delta))) if delta.size else 0.0
    return {
        "count": int(left.size),
        "error_l2": error_l2,
        "reference_l2": reference_l2,
        "relative_l2": error_l2 / reference_l2 if reference_l2 else None,
        "max_abs_error": maximum,
        "reference_peak_abs": reference_peak,
        "max_abs_error_over_reference_peak": maximum / reference_peak if reference_peak else None,
    }


def coordinate_hash(values: np.ndarray) -> str:
    array = np.asarray(values, dtype="<f8")
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def modal_amplitude_map(port_power: dict[str, Any]) -> dict[tuple[str, int, int, str], complex]:
    orders = port_power.get("orders")
    if not isinstance(orders, list):
        raise TypeError("port_power.orders is missing")
    result: dict[tuple[str, int, int, str], complex] = {}
    for row in orders:
        key = (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"]))
        if key in result:
            raise ValueError(f"duplicate modal key: {key}")
        result[key] = _complex_pair(row["outgoing_amplitude"])
    return result


def _load_run(root: Path, nx: int) -> dict[str, Any]:
    run_dir = root / RUNS[nx]
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    manifest = _json(run_dir / "run_manifest.json")
    terminal = _json(run_dir / "run_summary.json")
    direct = _json(run_dir / "p6_condensed_direct_summary.json")
    resolved = _json(run_dir / "resolved_config.json")
    port = _json(run_dir / "numerical_output/port_power.json")
    volume = _json(run_dir / "numerical_output/volume_absorption.json")
    analytic = _json(run_dir / "numerical_output/flat_layer_reference.json")
    sample_metadata = _json(run_dir / "numerical_output/full3d_reference_samples.json")
    sample_path = run_dir / "numerical_output/full3d_reference_samples.npz"
    sample_hash = _sha256(sample_path)
    if sample_hash != sample_metadata.get("archive_sha256"):
        raise ValueError(f"field sample hash does not match its metadata: Nx{nx}")
    if sample_path.stat().st_size != sample_metadata.get("archive_bytes"):
        raise ValueError(f"field sample size does not match its metadata: Nx{nx}")
    with np.load(sample_path, allow_pickle=False) as archive:
        missing = set(SAMPLE_ARRAY_KEYS) - set(archive.files)
        if missing:
            raise ValueError(f"field sample arrays missing for Nx{nx}: {sorted(missing)}")
        samples = {key: archive[key].copy() for key in SAMPLE_ARRAY_KEYS}

    source_after = manifest.get("source_after", {})
    if terminal.get("exit_status") != 0 or terminal.get("status") != "finished":
        raise ValueError(f"Nx{nx} is not a natural exit-0 terminal run")
    if not direct.get("passed") or direct.get("errors"):
        raise ValueError(f"Nx{nx} direct numerical summary is not passed")
    if source_after.get("source_sha") != manifest.get("source_sha"):
        raise ValueError(f"Nx{nx} source_after does not match the executed source")
    if source_after.get("tracked_and_nonignored_untracked_clean") is not True:
        raise ValueError(f"Nx{nx} source_after is not recorded clean")
    axes = direct.get("mesh_evidence", {}).get("axis_cell_counts")
    if axes != [nx, 2, 234] or direct["mesh_evidence"].get("actual_global_cell_count") != nx * 2 * 234:
        raise ValueError(f"Nx{nx} actual mesh does not match its named axis count")
    if direct.get("mode_inventory", {}).get("active_mode_count") != 540:
        raise ValueError(f"Nx{nx} has an unexpected active mode count")

    files = {
        "run_manifest": run_dir / "run_manifest.json",
        "run_summary": run_dir / "run_summary.json",
        "direct_summary": run_dir / "p6_condensed_direct_summary.json",
        "resolved_config": run_dir / "resolved_config.json",
        "port_power": run_dir / "numerical_output/port_power.json",
        "volume_absorption": run_dir / "numerical_output/volume_absorption.json",
        "flat_layer_reference": run_dir / "numerical_output/flat_layer_reference.json",
        "field_sample_metadata": run_dir / "numerical_output/full3d_reference_samples.json",
        "field_sample_archive": sample_path,
    }
    return {
        "nx": nx,
        "run_dir": run_dir,
        "manifest": manifest,
        "terminal": terminal,
        "direct": direct,
        "resolved": resolved,
        "port": port,
        "volume": volume,
        "analytic": analytic,
        "sample_metadata": sample_metadata,
        "samples": samples,
        "amplitudes": modal_amplitude_map(port),
        "orders": {
            (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"])): row
            for row in port["orders"]
        },
        "file_identity": {
            key: {"path": str(path.relative_to(root)), "sha256": _sha256(path), "bytes": path.stat().st_size}
            for key, path in files.items()
        },
    }


def _field_comparison(candidate: np.ndarray, reference: np.ndarray, z_nm: np.ndarray) -> dict[str, Any]:
    result: dict[str, Any] = {"all_samples": complex_vector_metrics(candidate, reference)}
    if candidate.ndim == 4 and candidate.shape[0] == len(z_nm):
        result["per_z_plane"] = [
            {"z_nm": float(z), **complex_vector_metrics(candidate[i], reference[i])}
            for i, z in enumerate(z_nm)
        ]
    if candidate.ndim >= 1 and candidate.shape[-1] == 3:
        result["per_component_absolute"] = []
        for component, name in enumerate(("x", "y", "z")):
            metrics = complex_vector_metrics(candidate[..., component], reference[..., component])
            result["per_component_absolute"].append({
                "component": name,
                "error_l2": metrics["error_l2"],
                "max_abs_error": metrics["max_abs_error"],
                "reference_l2": metrics["reference_l2"],
                "relative_l2": metrics["relative_l2"],
                "relative_warning": (
                    "unstable_for_near_zero_reference_component"
                    if metrics["reference_l2"] is not None and metrics["reference_l2"] < 1e-8 * complex_vector_metrics(candidate, reference)["reference_l2"]
                    else None
                ),
            })
    return result


def _modal_comparison(candidate: dict[str, complex], reference: dict[str, complex], side: str) -> dict[str, Any]:
    candidate_keys = {key for key in candidate if key[0] == side}
    reference_keys = {key for key in reference if key[0] == side}
    if candidate_keys != reference_keys:
        raise ValueError(f"modal inventory mismatch on {side}: {len(candidate_keys)} vs {len(reference_keys)}")
    keys = sorted(candidate_keys)
    current = np.asarray([candidate[key] for key in keys], dtype=np.complex128)
    baseline = np.asarray([reference[key] for key in keys], dtype=np.complex128)
    metrics = complex_vector_metrics(current, baseline)
    delta = np.abs(current - baseline)
    index = int(np.argmax(delta)) if delta.size else 0
    metrics["max_error_mode"] = list(keys[index]) if keys else None
    metrics["outgoing_amplitude_definition"] = (
        "top: auxiliary total-field projection minus incident projection; "
        "bottom: auxiliary total-field projection; no global phase fit"
    )
    return metrics


def _swap_reconciliation(authority: dict[str, Any], outer: dict[str, Any]) -> dict[str, Any]:
    delta = authority.get("global_swap_activity", {}).get("delta", {})
    pin = delta.get("pswpin_pages")
    pout = delta.get("pswpout_pages")
    tree_peak = authority.get("sampled_process_tree_swap_peak_bytes")
    state = authority.get("job_swap_activity")
    measured_zero = (
        state == "no_task_or_global_swap_observed"
        and type(pin) is int and pin == 0
        and type(pout) is int and pout == 0
        and tree_peak == 0
    )
    if measured_zero:
        interpretation = "tree and global counters support zero; original outer classification remains unchanged"
        classifier_gap = outer.get("result_classification") == "EVIDENCE_INCOMPLETE"
    elif state == "UNRESOLVED_global_activity_cannot_be_attributed":
        interpretation = "tree samples show zero task swap, but nonzero WSL-global page-in cannot be attributed to this run"
        classifier_gap = False
    else:
        interpretation = "not qualified as zero swap from the recorded fields"
        classifier_gap = False
    return {
        "outer_result_classification_preserved": outer.get("result_classification"),
        "outer_job_swap_qualification_preserved": outer.get("job_swap_qualification"),
        "watchdog_job_swap_activity": state,
        "sampled_process_tree_swap_peak_bytes": tree_peak,
        "global_pswpin_delta_pages": pin,
        "global_pswpout_delta_pages": pout,
        "measured_zero_swap_supported_by_available_fields": measured_zero,
        "outer_evidence_incomplete_due_to_old_classifier_contract": classifier_gap,
        "interpretation": interpretation,
        "scope": "global WSL swap counters are diagnostic and do not attribute global activity to the task",
    }


def _run_row(run: dict[str, Any]) -> dict[str, Any]:
    direct = run["direct"]
    terminal = run["terminal"]
    authority = terminal.get("resource_authority", {})
    port = run["port"]
    volume = run["volume"]
    mesh = direct["mesh_evidence"]
    matrix = direct.get("matrix", {})
    matrix_info = matrix.get("actual_matrix_info_after_solve", {})
    factor = direct.get("factor", {})
    residuals = direct.get("residuals", {})
    h = 1.0 / run["nx"]
    return {
        "nx": run["nx"],
        "hx_nm": h,
        "cells": mesh["actual_global_cell_count"],
        "source_sha": run["manifest"]["source_sha"],
        "input_sha256": run["manifest"]["input_sha256"],
        "physical_model_sha256": run["manifest"]["physical_model_sha256"],
        "resolved_config_sha256": run["manifest"]["resolved_config_sha256"],
        "active_modes": direct["mode_inventory"]["active_mode_count"],
        "mode_sha256": direct["mode_inventory"]["active_mode_sha256"],
        "R_port": port["R_total"],
        "T_port": port["T_total"],
        "A_port_balance": port["A_balance"],
        "R_plus_T": port["R_plus_T"],
        "A_volume": volume["A_volume_total"],
        "A_substrate": volume.get("A_volume_substrate"),
        "A_grating": volume.get("A_volume_grating"),
        "energy_closure_abs": volume["energy_closure_error_port_volume"],
        "analytic_R_port": run["analytic"]["port_planes"]["R_ref"],
        "analytic_T_port": run["analytic"]["port_planes"]["T_ref_at_bottom_reference_plane"],
        "analytic_A_port": run["analytic"]["port_planes"]["A_ref_between_reference_planes"],
        "A6_full_relative": residuals["original_A6_full_relative"],
        "A6_gate": residuals["original_A6_full_relative_gate"],
        "condensed_matrix_shape": matrix.get("shape"),
        "full_p6_storage_rows": matrix.get("full_p6_storage_rows"),
        "active_trace_rows": matrix.get("active_trace_rows"),
        "appended_port_rows": matrix.get("appended_port_rows"),
        "local_interior_rows_eliminated": matrix.get("local_interior_rows_eliminated"),
        "matrix_nz_used": matrix_info.get("nz_used"),
        "matrix_nz_allocated": matrix_info.get("nz_allocated"),
        "matrix_nz_unneeded": matrix_info.get("nz_unneeded"),
        "assembly_seconds": matrix.get("assembly_wall_seconds"),
        "factor_lifecycle_seconds": factor.get("solve_lifecycle_wall_seconds"),
        "factor_symbolic_calls": factor.get("symbolic_calls"),
        "factor_numeric_calls": factor.get("numeric_calls"),
        "factor_backend": factor.get("backend"),
        "factor_ordering": factor.get("preferred_ordering"),
        "factor_same_matrix_lifecycle": factor.get("same_matrix_lifecycle_verified"),
        "mumps_infog_raw": factor.get("mumps_info_after_solve", {}).get("infog"),
        "mumps_rinfog_raw": factor.get("mumps_info_after_solve", {}).get("rinfog"),
        "workflow_seconds": direct.get("elapsed_monotonic_seconds"),
        "rss_peak_bytes": authority.get("sampled_process_tree_rss_peak_bytes"),
        "tree_swap_peak_bytes": authority.get("sampled_process_tree_swap_peak_bytes"),
        "job_swap_activity": authority.get("job_swap_activity"),
        "global_pswpin_delta_pages": authority.get("global_swap_activity", {}).get("delta", {}).get("pswpin_pages"),
        "global_pswpout_delta_pages": authority.get("global_swap_activity", {}).get("delta", {}).get("pswpout_pages"),
        "outer_classification_original": terminal.get("result_classification"),
        "direct_worker_passed": direct.get("passed"),
        "zero_swap_reconciliation": _swap_reconciliation(authority, terminal),
    }


def build_report(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    loaded = {nx: _load_run(root, nx) for nx in (2, 4, 8)}
    evidence_dir = HERE
    v0_path = evidence_dir / "v0_source_identity_reconciliation.json"
    v1_path = evidence_dir / "v1_actual_n1e_ey_dispersion_symbol.json"
    v0 = _json(v0_path)
    v1 = _json(v1_path)
    v1_results = v1.get("numerical_results")
    if v1.get("status") != "BOUNDED_REFERENCE_CELL_SYMBOL_COMPLETE_ACTUAL_PRODUCTION_MPC_PORT_NOT_RUN":
        raise ValueError("V1 reference-cell symbol evidence has an unexpected status")
    expected_v1_cases = {
        (6, 0.5, 0.6), (6, 0.25, 0.6), (6, 0.125, 0.6),
        (6, 0.5, 10.0 / 17.0), (6, 0.25, 10.0 / 17.0),
        (6, 0.125, 10.0 / 17.0), (7, 0.5, 0.6), (8, 0.5, 0.6),
    }
    actual_v1_cases = {
        (int(row["degree"]), float(row["hx_nm"]), float(row["hz_nm"]))
        for row in v1_results
    } if isinstance(v1_results, list) else set()
    if actual_v1_cases != expected_v1_cases:
        raise ValueError(f"V1 actual reference-cell case inventory differs: {actual_v1_cases}")
    finest = loaded[8]
    baseline_config = finest["resolved"]
    common_sections = ("materials", "incidence", "boundary", "geometry")
    common_identity = {
        section: all(loaded[nx]["resolved"].get(section) == baseline_config.get(section) for nx in (2, 4, 8))
        for section in common_sections
    }
    if not all(common_identity.values()):
        raise ValueError(f"physical setup changed across flat runs: {common_identity}")
    if len({run["direct"]["mode_inventory"]["active_mode_sha256"] for run in loaded.values()}) != 1:
        raise ValueError("active mode hash differs across Nx cases")
    if len({len(run["amplitudes"]) for run in loaded.values()}) != 1:
        raise ValueError("modal output counts differ across Nx cases")
    if len({
        json.dumps(run["analytic"]["port_planes"], sort_keys=True)
        for run in loaded.values()
    }) != 1:
        raise ValueError("analytic flat-layer port reference differs across Nx cases")

    reference_coords = finest["samples"]
    coordinate_keys = ("x_nm", "y_nm", "z_nm", "interface_z_nm")
    coord_exact = {
        nx: all(np.array_equal(loaded[nx]["samples"][key], reference_coords[key]) for key in coordinate_keys)
        for nx in (2, 4, 8)
    }
    if not all(coord_exact.values()):
        raise ValueError(f"field samples are not on identical coordinates: {coord_exact}")

    pairs: dict[str, Any] = {}
    for nx, reference_nx in ((2, 4), (2, 8), (4, 8)):
        run = loaded[nx]
        comparison_run = loaded[reference_nx]
        samples = run["samples"]
        comparison_samples = comparison_run["samples"]
        ports: dict[str, Any] = {}
        for side in ("top", "bottom"):
            ports[side] = _modal_comparison(
                run["amplitudes"], comparison_run["amplitudes"], side
            )
        top_r = run["amplitudes"][("top", 0, 0, "s")]
        top_r_ref = comparison_run["amplitudes"][("top", 0, 0, "s")]
        bottom_t = run["amplitudes"][("bottom", 0, 0, "s")]
        bottom_t_ref = comparison_run["amplitudes"][("bottom", 0, 0, "s")]
        analytic = run["analytic"]["port_planes"]
        r_analytic = _complex_pair(run["analytic"]["r_amplitude"])
        t_analytic = _complex_pair(run["analytic"]["t_amplitude"])
        pairs[f"nx{nx}_vs_nx{reference_nx}"] = {
            "field_samples": {
                "coordinate_match_exact": True,
                "sample_side_material": "air; all requested z planes are above interface_z=0 nm",
                "E_V_per_m": _field_comparison(samples["E_V_per_m"], comparison_samples["E_V_per_m"], samples["z_nm"]),
                "H_A_per_m": _field_comparison(samples["H_A_per_m"], comparison_samples["H_A_per_m"], samples["z_nm"]),
                "E_t_interface_V_per_m": complex_vector_metrics(samples["E_t_interface_V_per_m"], comparison_samples["E_t_interface_V_per_m"]),
                "H_t_interface_A_per_m": complex_vector_metrics(samples["H_t_interface_A_per_m"], comparison_samples["H_t_interface_A_per_m"]),
            },
            "port_modal_outgoing_amplitudes": {
                "complex_amplitudes": True,
                "phase_alignment": "none",
                "all_matching_auto_propagating_modes": ports,
                "zero_order_s": {
                    "r_candidate": [top_r.real, top_r.imag],
                    "r_reference_run": [top_r_ref.real, top_r_ref.imag],
                    "r_abs_difference": abs(top_r - top_r_ref),
                    "r_reference": [r_analytic.real, r_analytic.imag],
                    "reference_run_nx": reference_nx,
                    "r_candidate_error_vs_analytic_abs": abs(top_r - r_analytic),
                    "r_reference_run_error_vs_analytic_abs": abs(top_r_ref - r_analytic),
                    "t_candidate": [bottom_t.real, bottom_t.imag],
                    "t_reference_run": [bottom_t_ref.real, bottom_t_ref.imag],
                    "t_abs_difference": abs(bottom_t - bottom_t_ref),
                    "t_reference": [t_analytic.real, t_analytic.imag],
                    "t_candidate_error_vs_analytic_abs": abs(bottom_t - t_analytic),
                    "t_reference_run_error_vs_analytic_abs": abs(bottom_t_ref - t_analytic),
                    "R_port_error_vs_analytic_abs": abs(run["port"]["R_total"] - analytic["R_ref"]),
                    "T_port_error_vs_analytic_abs": abs(run["port"]["T_total"] - analytic["T_ref_at_bottom_reference_plane"]),
                    "A_port_error_vs_analytic_abs": abs(run["port"]["A_balance"] - analytic["A_ref_between_reference_planes"]),
                },
            },
        }

    rows = [_run_row(loaded[nx]) for nx in (2, 4, 8)]
    finest_row = rows[-1]
    for row in rows:
        for quantity in ("R_port", "T_port", "A_port_balance", "A_volume"):
            row[f"{quantity}_difference_vs_nx8"] = row[quantity] - finest_row[quantity]
    changes = {}
    for quantity in ("R_port", "T_port", "A_port_balance", "A_volume"):
        changes[quantity] = {
            "nx2_to_nx4": rows[0][quantity] - rows[1][quantity],
            "nx4_to_nx8": rows[1][quantity] - rows[2][quantity],
            "successive_absolute_change_ratio": (
                abs(rows[0][quantity] - rows[1][quantity]) / abs(rows[1][quantity] - rows[2][quantity])
                if rows[1][quantity] != rows[2][quantity]
                else None
            ),
        }

    ref_arrays = {
        key: {
            "values": reference_coords[key].tolist(),
            "sha256_le_f64": coordinate_hash(reference_coords[key]),
        }
        for key in coordinate_keys
    }
    report = {
        "schema": "task39extra.dispersion_flat_direct_calibration.v1",
        "status": "OFFLINE_FLAT_CALIBRATION_COMPLETE_AUTHORITY_LIMITED",
        "comparison": "same physical flat-layer case, x-only mesh refinement Nx2/Nx4/Nx8; no global phase alignment",
        "physics_and_identity": {
            "common_resolved_sections_exactly_equal": common_identity,
            "materials": baseline_config["materials"],
            "incidence": baseline_config["incidence"],
            "boundary": baseline_config["boundary"],
            "geometry": baseline_config["geometry"],
            "mode_count": 540,
            "mode_sha256": finest["direct"]["mode_inventory"]["active_mode_sha256"],
            "mode_policy": "all_auto_propagating_flat_inventory_q160; evanescent orders excluded",
            "full_dtn_authority": "LIMITED; only auto-propagating finite port inventory",
            "physical_model_sha256_varies_with_mesh": True,
        },
        "sample_coordinates": {
            "coordinate_match_exact_for_all_runs": coord_exact,
            "arrays": ref_arrays,
            "shape_z_y_x_component": list(reference_coords["E_V_per_m"].shape),
            "point_count": int(np.prod(reference_coords["E_V_per_m"].shape[:-1])),
            "z_planes_nm": reference_coords["z_nm"].tolist(),
            "y_planes_nm": reference_coords["y_nm"].tolist(),
            "x_planes_nm": reference_coords["x_nm"].tolist(),
            "side_note": "all stored E/H sample planes are in air (z > interface_z=0 nm); port amplitudes separately cover top air and bottom lossy substrate",
        },
        "runs": {
            str(nx): {
                "run_id": run["manifest"]["run_id"],
                "source_sha": run["manifest"]["source_sha"],
                "source_after_clean_and_equal": True,
                "input_sha256": run["manifest"]["input_sha256"],
                "physical_model_sha256": run["manifest"]["physical_model_sha256"],
                "resolved_config_sha256": run["manifest"]["resolved_config_sha256"],
                "axes_cells": run["direct"]["mesh_evidence"]["axis_cell_counts"],
                "actual_cells": run["direct"]["mesh_evidence"]["actual_global_cell_count"],
                "axis_hashes": run["direct"]["mesh_evidence"]["axis_sha256_le_f64"],
                "mesh_plan_sha256": run["direct"]["mesh_evidence"]["mesh_plan_sha256"],
                "p6_summary_status": run["direct"]["result_classification"],
                "p6_summary_passed": run["direct"]["passed"],
                "operator_scope": run["direct"].get("operator_scope"),
                "outer_run_classification_preserved": run["terminal"]["result_classification"],
                "outer_exit_status": run["terminal"]["exit_status"],
                "quadrature_comparison": run["direct"].get("quadrature_comparison"),
                "matrix_and_factor": {
                    "matrix_shape": run["direct"]["matrix"].get("shape"),
                    "full_p6_storage_rows": run["direct"]["matrix"].get("full_p6_storage_rows"),
                    "active_trace_rows": run["direct"]["matrix"].get("active_trace_rows"),
                    "appended_port_rows": run["direct"]["matrix"].get("appended_port_rows"),
                    "local_interior_rows_eliminated": run["direct"]["matrix"].get("local_interior_rows_eliminated"),
                    "matrix_info_after_assembly": run["direct"]["matrix"].get("actual_matrix_info_after_assembly"),
                    "matrix_info_after_solve": run["direct"]["matrix"].get("actual_matrix_info_after_solve"),
                    "matrix_is_global_full_p6": run["direct"]["matrix"].get("global_full_p6_matrix"),
                    "matrix_has_dense_trace_dtn": run["direct"]["matrix"].get("dense_trace_dtn_matrix"),
                    "assembly_wall_seconds": run["direct"]["matrix"].get("assembly_wall_seconds"),
                    "factor": run["direct"].get("factor"),
                    "raw_mumps_info_is_diagnostic_not_memory_gate": True,
                },
                "resource_authority": {
                    key: run["terminal"].get("resource_authority", {}).get(key)
                    for key in (
                        "rss_hard_limit_bytes",
                        "sampled_process_tree_rss_peak_bytes",
                        "sampled_process_tree_swap_peak_bytes",
                        "job_swap_activity",
                        "global_swap_delta_policy",
                        "global_swap_activity",
                    )
                },
                "swap_classification_reconciliation": _swap_reconciliation(
                    run["terminal"].get("resource_authority", {}), run["terminal"]
                ),
                "file_identity": run["file_identity"],
            }
            for nx, run in loaded.items()
        },
        "pairwise_port_and_field_comparison": pairs,
        "port_power_and_absorption": {
            "by_run": {
                str(nx): {
                    "R_port": run["port"]["R_total"],
                    "T_port": run["port"]["T_total"],
                    "A_balance_port": run["port"]["A_balance"],
                    "R_plus_T": run["port"]["R_plus_T"],
                    "A_volume_total": run["volume"]["A_volume_total"],
                    "regions": {
                        name: {
                            "cell_count": region.get("cell_count"),
                            "volume_nm3": region.get("volume_nm3"),
                            "A_volume": region.get("A_volume"),
                            "material_label": region.get("material_label"),
                            "status": region.get("status"),
                        }
                        for name, region in run["volume"]["regions"].items()
                    },
                    "energy_closure_port_minus_volume": run["volume"]["energy_closure_error_port_volume"],
                    "flat_analytic_port_reference": run["analytic"]["port_planes"],
                    "A6_full_relative": run["direct"]["residuals"]["original_A6_full_relative"],
                    "A6_gate": run["direct"]["residuals"]["original_A6_full_relative_gate"],
                }
                for nx, run in loaded.items()
            },
            "trend_differences": changes,
            "interpretation": "substrate is the only absorbing region in these flat inputs; grating tag has zero cells and no measured grating absorption",
        },
        "hx_trend": {
            "hx_nm_by_nx": {str(nx): 1.0 / nx for nx in (2, 4, 8)},
            "observed_changes": changes,
            "interpretation": "Nx2 differs strongly from Nx4; Nx4/Nx8 values are close. Three points do not establish an asymptotic convergence order or a rigorous discretization-error bound.",
        },
        "v1_actual_fe_symbol_evidence": {
            "status": v1["status"],
            "scope": v1["scope"],
            "historical_run_id": v1["identity"].get("historical_run_id"),
            "historical_run_source_sha": v1["identity"].get("historical_run_source_sha"),
            "historical_full600_input_sha256": v1["identity"].get("input_sha256"),
            "historical_direct_summary_sha256": v1["identity"].get("direct_summary_sha256"),
            "reference_symbol_file": {
                "path": str(v1_path.relative_to(root)),
                "sha256": _sha256(v1_path),
                "bytes": v1_path.stat().st_size,
            },
            "quadrature": v1["quadrature"],
            "selected_results": [
                {
                    key: row.get(key)
                    for key in (
                        "degree",
                        "hx_nm",
                        "hz_nm",
                        "J_diagonal_nm",
                        "lambda_nm_minus2",
                        "target_kx2_nm_minus2",
                        "relative_lambda_over_kx2_minus_1",
                        "plan_delta_lambda_minus_kx2_over_k0_2",
                        "plane_wave_mass_overlap",
                        "generalized_eigenpair_relative_residual",
                        "K_hermitian_relative_defect",
                        "M_hermitian_relative_defect",
                        "longdouble_nmant",
                        "roundoff_scale_eps_times_max_condition",
                    )
                }
                for row in v1_results
            ],
            "scope_limit": "canonical reference-cell symbol only; production MPC/orientation and actual grating port remain NOT_RUN",
        },
        "v0_provenance_reconciliation": {
            "status": v0.get("status"),
            "scope": v0.get("scope"),
            "file": {
                "path": str(v0_path.relative_to(root)),
                "sha256": _sha256(v0_path),
                "bytes": v0_path.stat().st_size,
            },
            "limitations": v0.get("limitations"),
        },
        "linear_error_limitations": [
            "P6 sampled field and modal differences are finite cross-mesh observations, not a rigorous interpolation or continuum error bound.",
            "No fitted global complex phase is removed; the reported complex differences retain phase error.",
            "The 320 field points are selected samples, not a full-field norm over the domain.",
            "The small flat model validates this flat-layer calibration only; it does not qualify the original grating or full evanescent DtN operator.",
        ],
        "evidence_read_scope": {
            "read": ["three small terminal summaries", "three resolved configs", "three direct summaries", "three watchdog summaries", "three port/volume outputs", "three 33-34 KiB field sample archives", "existing V0/V1 small records"],
            "not_read": ["resource streams", "large field/VTU files", "matrix/factor/checkpoint", "historical NPZ/full-field artifacts"],
        },
    }
    return report, rows, build_modal_rows(loaded)


def build_modal_rows(loaded: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    reference_keys = set(loaded[8]["orders"])
    if any(set(run["orders"]) != reference_keys for run in loaded.values()):
        raise ValueError("per-order R/T output inventory differs among flat runs")
    rows: list[dict[str, Any]] = []
    for side, m, n, polarization in sorted(reference_keys):
        row: dict[str, Any] = {
            "side": side,
            "m": m,
            "n": n,
            "polarization": polarization,
        }
        for nx in (2, 4, 8):
            record = loaded[nx]["orders"][(side, m, n, polarization)]
            amplitude = _complex_pair(record["outgoing_amplitude"])
            row[f"r_re_nx{nx}"] = amplitude.real
            row[f"r_im_nx{nx}"] = amplitude.imag
            row[f"R_nx{nx}"] = record.get("R")
            row[f"T_nx{nx}"] = record.get("T")
            row[f"power_ratio_nx{nx}"] = record.get("power_ratio")
            row[f"propagating_nx{nx}"] = record.get("propagating")
        for left, right in ((2, 4), (2, 8), (4, 8)):
            a_left = _complex_pair(
                loaded[left]["orders"][(side, m, n, polarization)]["outgoing_amplitude"]
            )
            a_right = _complex_pair(
                loaded[right]["orders"][(side, m, n, polarization)]["outgoing_amplitude"]
            )
            row[f"amplitude_abs_difference_nx{left}_nx{right}"] = abs(a_left - a_right)
            for quantity in ("R", "T", "power_ratio"):
                v_left = loaded[left]["orders"][(side, m, n, polarization)].get(quantity)
                v_right = loaded[right]["orders"][(side, m, n, polarization)].get(quantity)
                row[f"{quantity}_difference_nx{left}_nx{right}"] = (
                    float(v_left) - float(v_right)
                    if v_left is not None and v_right is not None
                    else None
                )
        rows.append(row)
    return rows


def write_outputs(root: Path, output_dir: Path) -> None:
    report, rows, modal_rows = build_report(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "flat_calibration.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    csv_path = output_dir / "directional_grid_comparison.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    modal_path = output_dir / "flat_modal_orders.csv"
    with modal_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(modal_rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(modal_rows)
    resource_scope = {
        "schema": "task39extra.dispersion_validation_resource_scope.v1",
        "status": "OFFLINE_SMALL_METADATA_RECONCILIATION",
        "v0_outer_classification": report["v0_provenance_reconciliation"]["status"],
        "v0_run_summary_preserved": True,
        "flat_runs": {
            nx: {
                "run_id": run["run_id"],
                "source_sha": run["source_sha"],
                "outer_result_classification_preserved": run["outer_run_classification_preserved"],
                "direct_solver_passed": run["p6_summary_passed"],
                "operator_authority": run["operator_scope"],
                "resource_authority": run["resource_authority"],
                "swap_classification_reconciliation": run["swap_classification_reconciliation"],
            }
            for nx, run in report["runs"].items()
        },
        "source_classification_fix": {
            "code": "src/runners/task038_launcher.py::_zero_swap_is_qualified",
            "source_file_sha256": _sha256(root / "src/runners/task038_launcher.py"),
            "focused_test": "src/test/test_task39extra_dispersion_flat_direct.py::test_zero_swap_classifier_accepts_both_watchdog_contracts_fail_closed",
            "focused_test_file_sha256": _sha256(root / "src/test/test_task39extra_dispersion_flat_direct.py"),
            "accepts_legacy_watchdog_state": "zero_supported_by_zero_global_activity",
            "accepts_measured_tree_zero_state_only_when": [
                "job_swap_activity == no_task_or_global_swap_observed",
                "global pswpin_pages == 0",
                "global pswpout_pages == 0",
                "sampled_process_tree_swap_peak_bytes == 0",
            ],
            "historical_run_summaries_rewritten": False,
            "attribution_of_global_pagein_to_task": False,
        },
        "read_scope": report["evidence_read_scope"],
    }
    (output_dir / "resource_and_scope.json").write_text(
        json.dumps(resource_scope, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()
    write_outputs(args.root.resolve(), args.output_dir.resolve())


if __name__ == "__main__":
    main()
