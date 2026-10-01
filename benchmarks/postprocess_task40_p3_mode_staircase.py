"""Compare the saved Task40 G0 M0/M1/M2 mode-staircase fields offline."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks.postprocess_task40_p1_saved_fields_common_subcells import (
    RunInput,
    _load_run,
    _qualified_environment,
    _read_json,
    _sha256,
    _write_json,
)
from src.postprocessing.full3d_reference import (
    _sample_distributed_function,
    reference_plane_sides,
)
from src.postprocessing.task40_saved_field_h_comparison import (
    compare_common_subcell_volume,
    compare_material_interface_traces,
    restore_p6_total_field,
    total_field_sample_witness,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_M0 = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g0_iterative_review_v1__full3d_iterative__mpi1__Mna/"
    "20260930T102148.356966Z"
)
DEFAULT_M1 = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g0_manual_m1_f2_v1__full3d_iterative__mpi1__Mna/"
    "20261001T135923.003185Z"
)
DEFAULT_M2 = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g0_manual_m2_f3_v1__full3d_iterative__mpi1__Mna/"
    "20261001T154625.204407Z"
)
DEFAULT_M1_RECHECK = Path(
    "docs/task40extra_0p7nm_engineering/outcomes/records/g0_m1_offline_recheck_v1.json"
)
DEFAULT_OUTPUT = Path(
    "docs/task40extra_0p7nm_engineering/outcomes/records/channel_study_v2.json"
)

FIELD_LIMIT = 3.0e-3
POWER_LIMIT = 1.0e-4
SIGNIFICANT_MODE_LIMIT = 1.0e-2
SIGNIFICANCE_POWER_RATIO = 1.0e-8
GATE_FIELDS = (
    "E_total",
    "E_scattered",
    "H_total",
    "H_scattered",
    "scaled_curl_E_total",
    "scaled_curl_E_scattered",
)
POWER_FIELDS = ("R_total", "T_total", "A_balance", "A_volume_total")


def _resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _numerical_dir(run: RunInput) -> Path:
    path = Path(run.manifest["numerical_output_directory"])
    return path.resolve() if path.is_absolute() else (run.root / path).resolve()


def _mode_key(row: dict[str, Any]) -> tuple[str, int, int, str]:
    m = row["m"] if "m" in row else row["order_m"]
    n = row["n"] if "n" in row else row["order_n"]
    return (
        str(row["side"]),
        int(m),
        int(n),
        str(row["polarization"]),
    )


def _complex_pair(value: Any, *, field: str) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"mode field {field} is not a real/imaginary pair")
    result = complex(float(value[0]), float(value[1]))
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError(f"mode field {field} is nonfinite")
    return result


def _mode_inventory(run: RunInput, expected_count: int) -> tuple[dict[tuple[str, int, int, str], dict[str, Any]], dict[str, Any]]:
    numerical = _numerical_dir(run)
    path = numerical / "dtn_port_diffraction_orders_3d.json"
    payload = _read_json(path)
    records = payload.get("orders")
    if not isinstance(records, list) or len(records) != expected_count:
        raise ValueError(f"{run.label}: expected {expected_count} ordered modes")
    by_key: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    complex_fields = (
        "alpha",
        "gamma",
        "beta",
        "incident_projection",
        "auxiliary_amplitude_total_projection",
        "outgoing_amplitude",
        "outgoing_amplitude_at_boundary",
        "boundary_phase",
    )
    for row in records:
        key = _mode_key(row)
        if key in by_key:
            raise ValueError(f"{run.label}: duplicate mode key {key}")
        for name in complex_fields:
            _complex_pair(row[name], field=name)
        for name in ("modal_power_code_units", "power_ratio", "R", "T"):
            value = float(row[name])
            if not math.isfinite(value):
                raise ValueError(f"{run.label}: nonfinite {name} for mode {key}")
        by_key[key] = row
    metrics = payload.get("metrics", {})
    if int(metrics.get("dtn_port_mode_count", -1)) != expected_count:
        raise ValueError(f"{run.label}: mode-output count differs from its metrics")
    manifest_path = run.root / "task40q4_ordered_mode_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"{run.label}: ordered mode manifest is missing")
    manifest = _read_json(manifest_path)
    manifest_modes = manifest.get("modes")
    manifest_keys = [_mode_key(row) for row in manifest_modes] if isinstance(manifest_modes, list) else []
    output_keys = [_mode_key(row) for row in records]
    if (
        manifest.get("mode_count") != expected_count
        or len(manifest_keys) != expected_count
        or manifest_keys != output_keys
    ):
        raise ValueError(f"{run.label}: ordered manifest keys/count differ from saved mode outputs")
    facts = {
        "mode_count": len(records),
        "propagating_count": sum(bool(row["propagating"]) for row in records),
        "power_carrying_count": sum(bool(row["power_carrying"]) for row in records),
        "mode_output": str(path),
        "mode_output_sha256": _sha256(path),
        "ordered_mode_manifest": str(manifest_path),
        "ordered_mode_manifest_sha256": _sha256(manifest_path),
        "records": records,
        "metrics": metrics,
    }
    return by_key, facts


def _expected_manual_keys(max_m: int, max_n: int) -> set[tuple[str, int, int, str]]:
    return {
        (side, m, n, polarization)
        for side in ("top", "bottom")
        for m in range(-max_m, max_m + 1)
        for n in range(-max_n, max_n + 1)
        for polarization in ("s", "p")
    }


def _diff_paths(first: Any, second: Any, prefix: str = "") -> set[str]:
    if isinstance(first, dict) and isinstance(second, dict):
        changes: set[str] = set()
        for key in sorted(set(first) | set(second)):
            child = f"{prefix}/{key}" if prefix else key
            if key not in first or key not in second:
                changes.add(child)
            else:
                changes.update(_diff_paths(first[key], second[key], child))
        return changes
    if isinstance(first, list) and isinstance(second, list):
        return set() if first == second else {prefix}
    return set() if first == second else {prefix}


def _validate_resolved_configs(runs: dict[str, RunInput]) -> dict[str, Any]:
    expected: dict[str, set[str]] = {
        "M0_to_M1": {
            "boundary/dtn_order_policy",
            "boundary/dtn_manual_order_max_m",
            "boundary/dtn_manual_order_max_n",
            "solver/preconditioner",
            "provenance/expected_output_parent",
            "provenance/input_sha256",
            "provenance/physical_model_sha256",
            "provenance/source_path",
            "run_id",
        },
        "M1_to_M2": {
            "boundary/dtn_manual_order_max_m",
            "boundary/dtn_manual_order_max_n",
            "output/diffraction_order_max_m",
            "output/diffraction_order_max_n",
            "provenance/expected_output_parent",
            "provenance/input_sha256",
            "provenance/physical_model_sha256",
            "provenance/source_path",
            "run_id",
        },
    }
    pairs = (("M0", "M1", "M0_to_M1"), ("M1", "M2", "M1_to_M2"))
    changes: dict[str, Any] = {}
    for first_label, second_label, pair_name in pairs:
        first, second = runs[first_label].resolved, runs[second_label].resolved
        different = _diff_paths(first, second)
        unexpected = different - expected[pair_name]
        if unexpected:
            raise ValueError(f"{pair_name}: unexpected resolved-config changes {sorted(unexpected)}")
        changes[pair_name] = {
            "changed_paths": sorted(different),
            "allowed_paths": sorted(expected[pair_name]),
            "unexpected_paths": sorted(unexpected),
            "physical_sections_equal": {
                name: first.get(name) == second.get(name)
                for name in ("geometry", "materials", "incidence", "dimension", "discretization", "method")
            },
        }
        if not all(changes[pair_name]["physical_sections_equal"].values()):
            raise ValueError(f"{pair_name}: geometry/material/incidence/discretization changed")

    m0_boundary, m1_boundary, m2_boundary = (
        runs[label].resolved["boundary"] for label in ("M0", "M1", "M2")
    )
    if m0_boundary.get("dtn_order_policy") != "auto_propagating":
        raise ValueError("M0 is not the frozen auto_propagating baseline")
    for boundary, max_m, max_n in ((m1_boundary, 7, 1), (m2_boundary, 8, 2)):
        if (
            boundary.get("dtn_order_policy") != "manual"
            or boundary.get("dtn_manual_order_max_m") != max_m
            or boundary.get("dtn_manual_order_max_n") != max_n
        ):
            raise ValueError("manual M1/M2 boundary cutoffs do not match the declared staircase")
    for label, max_m, max_n in (("M0", 7, 1), ("M1", 7, 1), ("M2", 8, 2)):
        output = runs[label].resolved["output"]
        if output.get("diffraction_order_max_m") != max_m or output.get("diffraction_order_max_n") != max_n:
            raise ValueError(f"{label}: output-order window differs from its expected mode window")
    return changes


def _sample_quantities(run: RunInput, field: Any) -> dict[str, np.ndarray]:
    samples = run.samples
    x = np.asarray(samples["x_nm"], dtype=np.float64)
    y = np.asarray(samples["y_nm"], dtype=np.float64)
    z = np.asarray(samples["z_nm"], dtype=np.float64)
    zz, yy, xx = np.meshgrid(z, y, x, indexing="ij")
    points = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    sides = reference_plane_sides(len(z), len(x) * len(y))
    curl = _sample_distributed_function(field.curl, points, sides).reshape((-1, 3))

    from src.common.analytic_fields_3d import (
        electric_field_code_values,
        magnetic_field_code_values,
    )

    scale_e = float(run.cfg.electric_field_scale_V_per_m)
    scale_h = float(run.cfg.magnetic_field_scale_A_per_m)
    background_e = electric_field_code_values(run.cfg, points) * scale_e
    background_h_code = magnetic_field_code_values(run.cfg, points)
    background_h = background_h_code * scale_h
    e_total = np.asarray(samples["E_V_per_m"], dtype=np.complex128).reshape((-1, 3))
    h_total = np.asarray(samples["H_A_per_m"], dtype=np.complex128).reshape((-1, 3))
    curl_total = curl * scale_e
    curl_scattered = (curl - 1j * run.cfg.k0 * run.cfg.mu_r * background_h_code) * scale_e
    return {
        "E_total": e_total,
        "E_scattered": e_total - background_e,
        "H_total": h_total,
        "H_scattered": h_total - background_h,
        "scaled_curl_E_total": curl_total / run.cfg.k0,
        "scaled_curl_E_scattered": curl_scattered / run.cfg.k0,
    }


def _norm_record(first: np.ndarray, second: np.ndarray) -> dict[str, float]:
    difference = float(np.linalg.norm((second - first).ravel()))
    first_norm = float(np.linalg.norm(first.ravel()))
    second_norm = float(np.linalg.norm(second.ravel()))
    relative = difference / max(second_norm, np.finfo(np.float64).tiny)
    return {
        "first_l2_norm": first_norm,
        "second_l2_norm": second_norm,
        "difference_l2_norm": difference,
        "relative_to_second": relative,
    }


def _sample_comparison(
    first_run: RunInput,
    second_run: RunInput,
    first_field: Any,
    second_field: Any,
) -> dict[str, Any]:
    for coordinate in ("x_nm", "y_nm", "z_nm"):
        if not np.array_equal(first_run.samples[coordinate], second_run.samples[coordinate]):
            raise ValueError(f"{first_run.label}/{second_run.label}: reference sample {coordinate} differs")
    if first_run.samples["E_V_per_m"].shape != second_run.samples["E_V_per_m"].shape:
        raise ValueError("fixed sample array shapes differ")
    first_values = _sample_quantities(first_run, first_field)
    second_values = _sample_quantities(second_run, second_field)
    z_count = len(first_run.samples["z_nm"])
    y_count = len(first_run.samples["y_nm"])
    x_count = len(first_run.samples["x_nm"])
    metrics: dict[str, Any] = {}
    for name in GATE_FIELDS:
        left = first_values[name].reshape((z_count, y_count, x_count, 3))
        right = second_values[name].reshape((z_count, y_count, x_count, 3))
        overall = _norm_record(left, right)
        per_plane = [_norm_record(left[i], right[i]) for i in range(z_count)]
        metrics[name] = {
            **overall,
            "max_z_plane_relative_to_second": max(
                (record["relative_to_second"] for record in per_plane), default=0.0
            ),
            "per_z_plane": [
                {"z_nm": float(z), **record}
                for z, record in zip(first_run.samples["z_nm"], per_plane)
            ],
        }
    return {
        "method": "same-coordinate saved full3d_reference_samples; total H independently witnessed against direct UFL curl(E)",
        "sample_shape_z_y_x_component": list(first_run.samples["E_V_per_m"].shape),
        "sample_count": int(np.prod(first_run.samples["E_V_per_m"].shape[:3])),
        "sample_coordinates_sha256": hashlib.sha256(
            b"".join(
                np.asarray(first_run.samples[name], dtype=np.float64).tobytes()
                for name in ("x_nm", "y_nm", "z_nm")
            )
        ).hexdigest(),
        "metrics": metrics,
        "six_field_sample_gate": {
            "limit_relative_l2": FIELD_LIMIT,
            "max_overall_relative_to_second": max(
                metrics[name]["relative_to_second"] for name in GATE_FIELDS
            ),
            "max_z_plane_relative_to_second": max(
                metrics[name]["max_z_plane_relative_to_second"] for name in GATE_FIELDS
            ),
            "pass": all(
                metrics[name]["relative_to_second"] <= FIELD_LIMIT
                for name in GATE_FIELDS
            ),
            "all_z_planes_diagnostic_pass": all(
                metrics[name]["max_z_plane_relative_to_second"] <= FIELD_LIMIT
                for name in GATE_FIELDS
            ),
        },
    }


def _mode_comparison(
    first: dict[tuple[str, int, int, str], dict[str, Any]],
    second: dict[tuple[str, int, int, str], dict[str, Any]],
    baseline: dict[tuple[str, int, int, str], dict[str, Any]],
    incident_amplitude: float,
) -> dict[str, Any]:
    common_propagating = sorted(
        key
        for key in set(first) & set(second) & set(baseline)
        if bool(first[key]["propagating"])
        and bool(second[key]["propagating"])
        and bool(baseline[key]["propagating"])
    )
    if len(common_propagating) != 80:
        raise ValueError(f"expected 80 common propagating channels, found {len(common_propagating)}")
    significant = {
        key
        for key, row in baseline.items()
        if bool(row["propagating"]) and float(row["power_ratio"]) >= SIGNIFICANCE_POWER_RATIO
    }
    rows = []
    for key in common_propagating:
        first_row, second_row, baseline_row = first[key], second[key], baseline[key]
        amplitude_first = _complex_pair(
            first_row["outgoing_amplitude_at_boundary"], field="outgoing_amplitude_at_boundary"
        )
        amplitude_second = _complex_pair(
            second_row["outgoing_amplitude_at_boundary"], field="outgoing_amplitude_at_boundary"
        )
        delta = abs(amplitude_second - amplitude_first)
        baseline_power_ratio = float(baseline_row["power_ratio"])
        rows.append(
            {
                "key": list(key),
                "propagating_in_all_sets": True,
                "significant_by_frozen_M0_rule": key in significant,
                "M0_power_ratio": baseline_power_ratio,
                "first_outgoing_amplitude_at_boundary": [amplitude_first.real, amplitude_first.imag],
                "second_outgoing_amplitude_at_boundary": [amplitude_second.real, amplitude_second.imag],
                "absolute_amplitude_difference": delta,
                "relative_difference_to_first_amplitude": delta
                / max(abs(amplitude_first), np.finfo(np.float64).tiny),
                "incident_normalized_amplitude_difference": delta / incident_amplitude,
                "first_power_ratio": float(first_row["power_ratio"]),
                "second_power_ratio": float(second_row["power_ratio"]),
            }
        )
    significant_rows = [row for row in rows if row["significant_by_frozen_M0_rule"]]
    weak_rows = [row for row in rows if not row["significant_by_frozen_M0_rule"]]
    absolute_deltas = [row["absolute_amplitude_difference"] for row in rows]
    relative_deltas = [row["relative_difference_to_first_amplitude"] for row in rows]
    return {
        "method": "keyed by (side,m,n,polarization); compare boundary-plane complex outgoing amplitudes",
        "common_propagating_mode_count": len(rows),
        "significant_mode_count": len(significant_rows),
        "weak_mode_count": len(weak_rows),
        "incident_amplitude_reference": incident_amplitude,
        "significance_rule": "M0 power_ratio >= 1e-8; propagating modes only",
        "statistics": {
            "max_absolute_amplitude_difference": max(absolute_deltas, default=0.0),
            "median_absolute_amplitude_difference": float(np.median(absolute_deltas)),
            "p95_absolute_amplitude_difference": float(np.percentile(absolute_deltas, 95)),
            "max_raw_relative_amplitude_difference": max(relative_deltas, default=0.0),
            "max_significant_relative_difference": max(
                (row["relative_difference_to_first_amplitude"] for row in significant_rows),
                default=0.0,
            ),
            "max_weak_absolute_amplitude_difference": max(
                (row["absolute_amplitude_difference"] for row in weak_rows), default=0.0
            ),
            "max_weak_incident_normalized_difference": max(
                (row["incident_normalized_amplitude_difference"] for row in weak_rows),
                default=0.0,
            ),
        },
        "significant_gate": {
            "limit_relative_amplitude": SIGNIFICANT_MODE_LIMIT,
            "max_relative_amplitude": max(
                (row["relative_difference_to_first_amplitude"] for row in significant_rows),
                default=0.0,
            ),
            "pass": all(
                row["relative_difference_to_first_amplitude"] <= SIGNIFICANT_MODE_LIMIT
                for row in significant_rows
            ),
            "keys": [row["key"] for row in significant_rows],
        },
        "all_common_propagating_mode_comparisons": rows,
    }


def _power_comparison(first: RunInput, second: RunInput) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in POWER_FIELDS:
        if name == "A_volume_total":
            left = first.official_volume.get(name)
            right = second.official_volume.get(name)
        else:
            left = first.official_power.get(name)
            right = second.official_power.get(name)
        if left is None or right is None:
            raise ValueError(f"official power field {name} is missing")
        left_float, right_float = float(left), float(right)
        absolute = abs(right_float - left_float)
        values[name] = {
            "first": left_float,
            "second": right_float,
            "second_minus_first": right_float - left_float,
            "absolute_difference": absolute,
            "limit_absolute": POWER_LIMIT,
            "pass": absolute <= POWER_LIMIT,
        }
    return {
        "source": "saved official DtN port R/T/A and volume absorption; no power re-evaluation",
        "metrics": values,
        "gate": {"limit_absolute": POWER_LIMIT, "pass": all(row["pass"] for row in values.values())},
    }


def _interface_gate(interface: dict[str, Any]) -> dict[str, Any]:
    worst: dict[str, Any] | None = None
    checked = 0
    for transition in interface["traces"]:
        for group in transition["material_tag_transition_groups"]:
            for side in group["same_side_cross_grid_traces"]:
                for name in GATE_FIELDS:
                    metric = side["fields"][name]
                    checked += 1
                    candidate = {
                        "plane_names": transition["plane_names"],
                        "axis": transition["axis"],
                        "coordinate_nm": transition["coordinate_nm"],
                        "side": side["side"],
                        "field": name,
                        "relative_to_second": float(metric["relative_to_g1"]),
                    }
                    if worst is None or candidate["relative_to_second"] > worst["relative_to_second"]:
                        worst = candidate
    maximum = 0.0 if worst is None else worst["relative_to_second"]
    return {
        "checked_trace_metric_count": checked,
        "worst_trace_metric": worst,
        "limit_relative_l2": FIELD_LIMIT,
        "pass": maximum <= FIELD_LIMIT,
        "no_two_sided_in_domain_trace": bool(interface["coverage"]["surfaces_skipped_at_mesh_exterior"]),
    }


def _pair_comparison(
    first_run: RunInput,
    second_run: RunInput,
    first_modes: dict[tuple[str, int, int, str], dict[str, Any]],
    second_modes: dict[tuple[str, int, int, str], dict[str, Any]],
    baseline_modes: dict[tuple[str, int, int, str], dict[str, Any]],
    incident_amplitude: float,
    *,
    progress_label: str,
) -> dict[str, Any]:
    print(f"P3 {progress_label}: restoring saved p6 fields and direct UFL curl(E)", flush=True)
    first_field = restore_p6_total_field(first_run.label, first_run.cfg, first_run.vector)
    second_field = restore_p6_total_field(second_run.label, second_run.cfg, second_run.vector)
    first_witness = total_field_sample_witness(
        first_field, first_run.samples, first_run.sample_metadata
    )
    second_witness = total_field_sample_witness(
        second_field, second_run.samples, second_run.sample_metadata
    )
    if not first_witness["pass"] or not second_witness["pass"]:
        raise ValueError(f"{progress_label}: restored fields do not witness saved E/H samples")
    volume = compare_common_subcell_volume(first_field, second_field, progress=True)
    sample = _sample_comparison(first_run, second_run, first_field, second_field)
    axes = tuple(
        np.unique(np.concatenate((first_field.axes[i], second_field.axes[i])))
        for i in range(3)
    )
    interface = compare_material_interface_traces(first_field, second_field, axes)
    power = _power_comparison(first_run, second_run)
    modes = _mode_comparison(
        first_modes, second_modes, baseline_modes, incident_amplitude
    )
    physical_volume = volume["metrics"]["physical_domain"]["quantities"]
    volume_gate = {
        "limit_relative_l2": FIELD_LIMIT,
        "metrics": {
            name: {
                "relative_to_second": float(physical_volume[name]["relative_to_g1"]),
                "pass": float(physical_volume[name]["relative_to_g1"]) <= FIELD_LIMIT,
            }
            for name in GATE_FIELDS
        },
        "pass": all(
            float(physical_volume[name]["relative_to_g1"]) <= FIELD_LIMIT
            for name in GATE_FIELDS
        ),
    }
    interface_gate = _interface_gate(interface)
    field_gate_pass = bool(volume_gate["pass"] and sample["six_field_sample_gate"]["pass"])
    all_pass = bool(
        field_gate_pass
        and power["gate"]["pass"]
        and modes["significant_gate"]["pass"]
        and first_witness["pass"]
        and second_witness["pass"]
    )
    del first_field, second_field
    gc.collect()
    return {
        "pair": [first_run.label, second_run.label],
        "saved_sample_witnesses": {first_run.label: first_witness, second_run.label: second_witness},
        "common_subcell_volume_comparison": volume,
        "fixed_sample_comparison": sample,
        "material_interface_trace_comparison": interface,
        "official_power_comparison": power,
        "common_propagating_mode_comparison": modes,
        "gates": {
            "volume_six_field_metrics": volume_gate,
            "fixed_samples_six_fields_overall": sample["six_field_sample_gate"],
            "saved_sample_witnesses": {
                first_run.label: first_witness["pass"],
                second_run.label: second_witness["pass"],
            },
            "official_R_T_A_balance_A_volume": power["gate"],
            "significant_common_propagating_mode_amplitudes": modes["significant_gate"],
            "overall_pair_observation": all_pass,
            "continuum_convergence_claim": False,
        },
        "diagnostics": {
            "per_z_plane_sample_changes": {
                name: {
                    "max_relative_to_second": sample["metrics"][name][
                        "max_z_plane_relative_to_second"
                    ],
                    "all_planes_under_0p3_percent": sample["six_field_sample_gate"][
                        "all_z_planes_diagnostic_pass"
                    ],
                }
                for name in GATE_FIELDS
            },
            "material_interface_trace_changes": {
                **interface_gate,
                "used_for_M_star_decision": False,
            },
        },
    }


def _run_artifacts(run: RunInput, mode_facts: dict[str, Any], recheck_path: Path | None) -> dict[str, Any]:
    numerical = _numerical_dir(run)
    paths = {
        "run_manifest": run.root / "run_manifest.json",
        "run_summary": run.root / "run_summary.json",
        "input_original": run.root / "input_original.dat",
        "resolved_config": run.root / "resolved_config.json",
        "retained_field_packet": run.root / "x2_retained_final.json",
        "retained_field_archive": run.vector_archive,
        "sample_metadata": numerical / "full3d_reference_samples.json",
        "sample_archive": run.sample_archive,
        "modal_power": numerical / "dtn_port_power_metrics_3d.json",
        "volume_absorption": numerical / "volume_absorption.json",
        "mode_orders": Path(mode_facts["mode_output"]),
    }
    amplitude_path = numerical / "dtn_auxiliary_amplitudes_3d.json"
    if amplitude_path.is_file():
        paths["auxiliary_amplitudes"] = amplitude_path
    if recheck_path is not None:
        paths["offline_recheck_record"] = recheck_path
    artifact_hashes = {
        name: {"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size}
        for name, path in paths.items()
    }
    return {
        "run_id": run.manifest["run_id"],
        "source_sha": run.manifest["source_sha"],
        "input_sha256": run.manifest["input_sha256"],
        "physical_model_sha256": run.manifest["physical_model_sha256"],
        "run_root": str(run.root),
        "original_run_summary": {
            "status": run.run_summary.get("status"),
            "result_classification": run.run_summary.get("result_classification"),
            "exit_status": run.run_summary.get("exit_status"),
            "official_result": run.run_summary.get("official_result"),
            "task_process_tree_swap_status": run.run_summary.get(
                "task40_swap_qualification", {}
            ).get("status"),
            "task_process_tree_peak_swap_bytes": run.run_summary.get(
                "task40_swap_qualification", {}
            ).get("process_tree_peak_swap_bytes"),
        },
        "offline_recheck_status": (
            None
            if run.offline_recheck_record is None
            else run.offline_recheck_record.get("offline_recheck_status")
        ),
        "official_result_reissued": False,
        "mode_count": mode_facts["mode_count"],
        "propagating_count": mode_facts["propagating_count"],
        "full_field_vector_sha256": run.vector_sha256,
        "artifact_hashes": artifact_hashes,
    }


def _git_facts() -> dict[str, Any]:
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
        return {"head": head, "status": status.splitlines()}
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"head": None, "status": None, "error": str(exc)}


def compare_mode_staircase(
    *,
    m0_root: Path,
    m1_root: Path,
    m2_root: Path,
    m1_offline_recheck: Path,
    output: Path,
    progress: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()
    environment = _qualified_environment()
    m0_root, m1_root, m2_root = map(_resolve, (m0_root, m1_root, m2_root))
    m1_offline_recheck = _resolve(m1_offline_recheck)
    runs = {
        "M0": _load_run("M0", m0_root),
        "M1": _load_run("M1", m1_root, offline_recheck=m1_offline_recheck),
        "M2": _load_run("M2", m2_root),
    }
    config_changes = _validate_resolved_configs(runs)
    mode_sets = {
        "M0": _mode_inventory(runs["M0"], 80),
        "M1": _mode_inventory(runs["M1"], 180),
        "M2": _mode_inventory(runs["M2"], 340),
    }
    mode_maps = {label: item[0] for label, item in mode_sets.items()}
    for label, max_m, max_n in (("M1", 7, 1), ("M2", 8, 2)):
        if set(mode_maps[label]) != _expected_manual_keys(max_m, max_n):
            raise ValueError(f"{label}: actual ordered mode keys differ from its manual rectangle")
    m0_keys = set(mode_maps["M0"])
    if m0_keys != {key for key in mode_maps["M1"] if mode_maps["M1"][key]["propagating"]}:
        raise ValueError("M1 did not retain exactly the frozen M0 propagating set")
    if m0_keys != {key for key in mode_maps["M2"] if mode_maps["M2"][key]["propagating"]}:
        raise ValueError("M2 did not retain exactly the frozen M0 propagating set")
    expected_significant = {
        ("top", -7, 0, "s"),
        ("top", -2, 0, "s"),
        ("top", -1, -1, "s"),
        ("top", -1, 0, "s"),
        ("top", -1, 1, "s"),
        ("top", 0, 0, "s"),
        ("bottom", -2, 0, "s"),
        ("bottom", -1, -1, "s"),
        ("bottom", -1, 0, "s"),
        ("bottom", -1, 1, "s"),
        ("bottom", 0, 0, "s"),
    }
    actual_significant = {
        key
        for key, row in mode_maps["M0"].items()
        if bool(row["propagating"])
        and float(row["power_ratio"]) >= SIGNIFICANCE_POWER_RATIO
    }
    if actual_significant != expected_significant:
        raise ValueError("M0 significant-mode selection differs from its frozen threshold inventory")
    incident_key = ("top", 0, 0, "s")
    incident_amplitude = abs(
        _complex_pair(mode_maps["M0"][incident_key]["incident_projection"], field="incident_projection")
    )
    if incident_amplitude <= np.finfo(np.float64).tiny:
        raise ValueError("M0 incident projection is unusable as an amplitude normalization")

    pair_results = {}
    for first_label, second_label, pair_name in (("M0", "M1", "M0_to_M1"), ("M1", "M2", "M1_to_M2")):
        pair_results[pair_name] = _pair_comparison(
            runs[first_label],
            runs[second_label],
            mode_maps[first_label],
            mode_maps[second_label],
            mode_maps["M0"],
            incident_amplitude,
            progress_label=pair_name,
        )

    m1_m2_pass = bool(pair_results["M1_to_M2"]["gates"]["overall_pair_observation"])
    result_status = "M2_SELECTED_STABLE" if m1_m2_pass else "CHANNEL_TRUNCATION_UNQUALIFIED_M3_CONDITIONAL"
    comparison_code = {
        "entrypoint": str(Path(__file__).resolve()),
        "entrypoint_sha256": _sha256(Path(__file__).resolve()),
        "p1_loader_sha256": _sha256(Path(__file__).resolve().with_name("postprocess_task40_p1_saved_fields_common_subcells.py")),
        "field_comparison_module": str(
            ROOT / "src/postprocessing/task40_saved_field_h_comparison.py"
        ),
        "field_comparison_module_sha256": _sha256(
            ROOT / "src/postprocessing/task40_saved_field_h_comparison.py"
        ),
        "worktree": _git_facts(),
    }
    m1_recheck_sha256 = _sha256(m1_offline_recheck)
    result = {
        "schema": "task40extra.p3.mode-staircase-saved-fields.v1",
        "status": result_status,
        "classification": "OFFLINE_SAVED_FIELD_COMPARISON; no PDE or factorization",
        "execution": {
            "status": "OFFLINE_SAVED_FIELD_POSTPROCESS_ONLY",
            "pde_started": False,
            "physical_operator_built": False,
            "factor_started": False,
            "ksp_started": False,
            "duration_seconds": time.monotonic() - started,
            "process_peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
            "abi": environment,
        },
        "decision_rule_timing": {
            "all_80_M1_M2_mode_deltas_were_explored_before_M0_significance_filter_lock": True,
            "disclosure": "The exploratory all-80 amplitude summary was inspected before the M0 power_ratio >= 1e-8 significance rule was fixed. This report applies that rule to the complete retained mode arrays and does not describe it as pre-registered.",
            "frozen_rule": "M0 propagating power_ratio >= 1e-8; keep and report every common propagating mode regardless of selection",
            "exploratory_all_80_M1_M2_summary": {
                "max_absolute_amplitude_difference": pair_results["M1_to_M2"]["common_propagating_mode_comparison"]["statistics"]["max_absolute_amplitude_difference"],
                "median_absolute_amplitude_difference": pair_results["M1_to_M2"]["common_propagating_mode_comparison"]["statistics"]["median_absolute_amplitude_difference"],
                "p95_absolute_amplitude_difference": pair_results["M1_to_M2"]["common_propagating_mode_comparison"]["statistics"]["p95_absolute_amplitude_difference"],
                "max_raw_relative_amplitude_difference": pair_results["M1_to_M2"]["common_propagating_mode_comparison"]["statistics"]["max_raw_relative_amplitude_difference"],
                "warning": "Raw relative changes on near-zero channels are diagnostic only; weak-channel absolute and incident-normalized changes remain in every mode row.",
            },
        },
        "frozen_baseline": {
            "run_id": runs["M0"].manifest["run_id"],
            "mode_output_sha256": mode_sets["M0"][1]["mode_output_sha256"],
            "significance_power_ratio_threshold": SIGNIFICANCE_POWER_RATIO,
            "selected_key_count": len(actual_significant),
            "selected_keys": [list(key) for key in sorted(actual_significant)],
            "incident_amplitude_reference_key": list(incident_key),
            "incident_amplitude_reference_magnitude": incident_amplitude,
        },
        "models": {
            label: {
                **_run_artifacts(
                    runs[label],
                    mode_sets[label][1],
                    m1_offline_recheck if label == "M1" else None,
                ),
                "resolved_mode_policy": runs[label].resolved["boundary"],
                "mode_output_metrics": mode_sets[label][1]["metrics"],
                "all_retained_mode_values": mode_sets[label][1]["records"],
            }
            for label in ("M0", "M1", "M2")
        },
        "configuration_comparison": config_changes,
        "mode_inventory": {
            label: {
                "mode_count": mode_sets[label][1]["mode_count"],
                "propagating_count": mode_sets[label][1]["propagating_count"],
                "power_carrying_count": mode_sets[label][1]["power_carrying_count"],
                "mode_output_sha256": mode_sets[label][1]["mode_output_sha256"],
                "ordered_mode_manifest_sha256": mode_sets[label][1]["ordered_mode_manifest_sha256"],
            }
            for label in ("M0", "M1", "M2")
        },
        "pairwise_saved_field_comparisons": pair_results,
        "p3_decision": {
            "M1_to_M2_stable": m1_m2_pass,
            "field_relative_limit": FIELD_LIMIT,
            "official_R_T_A_balance_A_volume_absolute_limit": POWER_LIMIT,
            "significant_mode_relative_amplitude_limit": SIGNIFICANT_MODE_LIMIT,
            "selected_M_star": "M2" if m1_m2_pass else None,
            "M3_action": "not_run; condition not met" if m1_m2_pass else "consider only if safe under the task resource gate",
            "continuum_convergence_claim": False,
            "interpretation": (
                "M2 is the more conservative measured truncation that meets the finite M1-to-M2 engineering comparisons."
                if m1_m2_pass
                else "The M1-to-M2 comparison did not meet every engineering threshold; M3 is conditional and is not started by this offline postprocessor."
            ),
        },
        "comparison_code": comparison_code,
    }
    _write_json(_resolve(output), result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m0-root", type=Path, default=DEFAULT_M0)
    parser.add_argument("--m1-root", type=Path, default=DEFAULT_M1)
    parser.add_argument("--m2-root", type=Path, default=DEFAULT_M2)
    parser.add_argument("--m1-offline-recheck", type=Path, default=DEFAULT_M1_RECHECK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = compare_mode_staircase(
        m0_root=args.m0_root,
        m1_root=args.m1_root,
        m2_root=args.m2_root,
        m1_offline_recheck=args.m1_offline_recheck,
        output=args.output,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "output": str(_resolve(args.output)),
                "M1_to_M2_gates": result["pairwise_saved_field_comparisons"]["M1_to_M2"]["gates"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
