#!/usr/bin/env python3
"""Hash-bound, no-phase-fit comparison of the existing D13 B/X/Y/Z outputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path("results/si_block_phi90_50x50_17x20_h120")
CASES = {
    "B": ("task40_phi90_13p5_D13_B_p6_direct_v1", "20261016T091948.653032Z"),
    "X": ("task40_phi90_13p5_D13_X_p6_direct_v1", "20261016T094950.200837Z"),
    "Y": ("task40_phi90_13p5_D13_Y_p6_direct_v1", "20261016T102453.831934Z"),
    "Z": ("task40_phi90_13p5_D13_Z_p6_direct_v1", "20261016T104423.676151Z"),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def array_sha256(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    return hashlib.sha256(contiguous.view(np.uint8)).hexdigest()


def norm_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    delta = candidate - reference
    ref_norm = float(np.linalg.norm(reference.ravel()))
    delta_norm = float(np.linalg.norm(delta.ravel()))
    return {
        "reference_l2": ref_norm,
        "delta_l2": delta_norm,
        "relative_l2_no_phase_fit": delta_norm / ref_norm if ref_norm else (0.0 if delta_norm == 0 else float("inf")),
        "max_abs_delta": float(np.max(np.abs(delta))),
    }


def complex_value(pair: list[float]) -> complex:
    return complex(float(pair[0]), float(pair[1]))


def mode_key(item: dict) -> tuple:
    return (item["side"], item["direction"], int(item["m"]), int(item["n"]), item["polarization"])


def read_case(label: str) -> dict:
    folder, stamp = CASES[label]
    run_dir = ROOT / f"{folder}__full3d_direct__mpi1__Mna" / stamp
    out = run_dir / "numerical_output"
    run_summary = json.loads((run_dir / "run_summary.json").read_text())
    direct = json.loads((run_dir / "p6_condensed_direct_summary.json").read_text())
    power = json.loads((out / "dtn_port_power_metrics_3d.json").read_text())
    absorption = json.loads((out / "volume_absorption.json").read_text())
    samples_meta = json.loads((out / "full3d_reference_samples.json").read_text())
    modal = json.loads((out / "dtn_port_diffraction_orders_3d.json").read_text())
    with np.load(out / "full3d_reference_samples.npz", allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    source_sha = (run_dir / "source_sha.txt").read_text().strip()
    input_sha = (run_dir / "input_sha256.txt").read_text().strip()
    physical_sha = (run_dir / "physical_model_sha256.txt").read_text().strip()
    resolved_sha = sha256_file(run_dir / "resolved_config.json")
    return {
        "label": label,
        "run_dir": str(run_dir),
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "result_classification": run_summary["result_classification"],
        "exit_status": run_summary["exit_status"],
        "elapsed_seconds": run_summary["resource_authority"]["elapsed_seconds"],
        "rss_peak_bytes": run_summary["resource_authority"]["sampled_process_tree_rss_peak_bytes"],
        "task_swap_peak_bytes": run_summary["resource_authority"]["sampled_process_tree_swap_peak_bytes"],
        "global_swap_delta_pages": run_summary["resource_authority"]["global_swap_activity"]["delta"],
        "operator_scope": direct["operator_scope"],
        "passed": direct["passed"],
        "full_dtn_status": direct["full_dtn_status"],
        "cells": direct["mesh_evidence"]["actual_global_cell_count"],
        "axis_counts": direct["mesh_evidence"]["axis_cell_counts"],
        "axis_sha256": direct["mesh_evidence"]["axis_sha256_le_f64"],
        "mode_count": power["active_mode_count"],
        "mode_sha256": power["active_mode_sha256"],
        "surface_quadrature_degree": direct["production_port_mpc_witness"][
            "dtn_quadrature_degree"
        ],
        "surface_quadrature_witness_status": direct["production_port_mpc_witness"][
            "status"
        ],
        "R_total": power["R_total"],
        "R00_s": power["R00_s"],
        "R00_p": power["R00_p"],
        "R00_total": power["R00_total"],
        "T_total": power["T_total"],
        "A_balance": power["A_balance"],
        "A_volume": absorption["A_volume_total"],
        "A_grating": absorption["A_grating"],
        "A_substrate": absorption["A_substrate"],
        "energy_closure_abs": abs(1.0 - power["R_total"] - power["T_total"] - absorption["A_volume_total"]),
        "residuals": direct["residuals"],
        "modal_metrics": power,
        "modal_orders": modal["orders"],
        "dtn_modal_reference": power["dtn_port_modal_reference"],
        "dtn_top_reference_z": power["dtn_port_top_reference_z"],
        "dtn_bottom_reference_z": power["dtn_port_bottom_reference_z"],
        "dtn_amplitude_convention": power["dtn_port_modal_amplitude_convention"],
        "port_power_output_scope": power["output_scope"],
        "samples_meta": samples_meta,
        "samples": arrays,
        "artifact_sha256": {
            "samples_npz": samples_meta["archive_sha256"],
            "samples_json": sha256_file(out / "full3d_reference_samples.json"),
            "power_metrics_json": sha256_file(out / "dtn_port_power_metrics_3d.json"),
            "volume_absorption_json": sha256_file(out / "volume_absorption.json"),
            "diffraction_orders_json": sha256_file(out / "dtn_port_diffraction_orders_3d.json"),
        },
    }


cases = {label: read_case(label) for label in CASES}
base = cases["B"]
coord_names = ("x_nm", "y_nm", "z_nm")
sample_names = ("E_V_per_m", "H_A_per_m", "E_t_interface_V_per_m", "H_t_interface_A_per_m")
base_mode_keys = [mode_key(item) for item in base["modal_orders"]]
identity_fields = ("side", "direction", "m", "n", "polarization", "medium", "alpha", "gamma", "beta", "kz", "vertical_sign", "propagating", "power_carrying", "refractive_index")
base_branch_identity = [{key: item[key] for key in identity_fields} for item in base["modal_orders"]]
comparisons = {}
for label in ("X", "Y", "Z"):
    cand = cases[label]
    coords = {}
    for name in coord_names:
        a, b = base["samples"][name], cand["samples"][name]
        coords[name] = {
            "exact_array_equal": bool(np.array_equal(a, b)),
            "shape": list(a.shape),
            "dtype": str(a.dtype),
            "B_sha256": array_sha256(a),
            f"{label}_sha256": array_sha256(b),
        }
    same_coords = all(v["exact_array_equal"] for v in coords.values())
    arrays = {}
    for name in sample_names:
        a, b = base["samples"][name], cand["samples"][name]
        arrays[name] = {"shape": list(a.shape), "dtype": str(a.dtype), **norm_metrics(a, b)}
    cand_keys = [mode_key(item) for item in cand["modal_orders"]]
    cand_branch_identity = [{key: item[key] for key in identity_fields} for item in cand["modal_orders"]]
    if cand_keys != base_mode_keys:
        raise SystemExit(f"{label}: ordered modal keys differ")
    if cand_branch_identity != base_branch_identity:
        raise SystemExit(f"{label}: modal branch/material identity differs")
    boundary_phase_exact = all(
        base["modal_orders"][i]["boundary_phase"]
        == cand["modal_orders"][i]["boundary_phase"]
        for i in range(len(base_mode_keys))
    )
    if not (
        base["dtn_modal_reference"]
        == cand["dtn_modal_reference"]
        and base["dtn_top_reference_z"] == cand["dtn_top_reference_z"]
        and base["dtn_bottom_reference_z"] == cand["dtn_bottom_reference_z"]
        and base["dtn_amplitude_convention"] == cand["dtn_amplitude_convention"]
        and boundary_phase_exact
    ):
        raise SystemExit(f"{label}: modal phase/reference convention differs")
    amp = {}
    power_delta = {"all_modes": {}, "propagating": {}, "power_carrying": {}}
    for field in ("outgoing_amplitude", "outgoing_amplitude_at_boundary", "auxiliary_amplitude_total_projection"):
        a = np.asarray([complex_value(item[field]) for item in base["modal_orders"]], dtype=np.complex128)
        b = np.asarray([complex_value(item[field]) for item in cand["modal_orders"]], dtype=np.complex128)
        amp[field] = norm_metrics(a, b)
        diffs = np.abs(b - a)
        tops = np.argsort(diffs)[-10:][::-1]
        amp[field]["largest_absolute_differences"] = [
            {"key": list(base_mode_keys[int(i)]), "abs_delta": float(diffs[int(i)])} for i in tops
        ]
    for cls_name, mask_fn in (
        ("all_modes", lambda item: True),
        ("propagating", lambda item: bool(item["propagating"])),
        ("power_carrying", lambda item: bool(item["power_carrying"])),
    ):
        selected = [i for i, item in enumerate(base["modal_orders"]) if mask_fn(item)]
        for value_name in ("R", "T"):
            diffs = [abs(float(cand["modal_orders"][i][value_name]) - float(base["modal_orders"][i][value_name])) for i in selected]
            max_position = int(np.argmax(diffs)) if diffs else None
            power_delta[cls_name][value_name] = {
                "count": len(selected),
                "max_abs_delta": max(diffs, default=0.0),
                "max_abs_delta_key": list(mode_key(base["modal_orders"][selected[max_position]])) if max_position is not None else None,
                "count_over_1e-6": sum(value > 1e-6 for value in diffs),
            }
    metrics = {}
    for name in ("R_total", "R00_s", "R00_p", "R00_total", "T_total", "A_balance", "A_volume", "A_grating", "A_substrate", "energy_closure_abs"):
        metrics[name] = {"B": base[name], label: cand[name], "absolute_delta": abs(cand[name] - base[name])}
    comparisons[label] = {
        "changed_axis": label.lower(),
        "only_axis_hash_changed_from_B": all(
            (base["axis_sha256"][axis] != cand["axis_sha256"][axis]) == (axis == label.lower())
            for axis in ("x", "y", "z")
        ),
        "same_sample_coordinates_exactly": same_coords,
        "sample_coordinates": coords,
        "sample_field_comparisons_no_phase_fit": arrays,
        "modal_ordered_branch_identity_exact": True,
        "modal_reference_planes_and_amplitude_convention_exact": True,
        "boundary_phase_exact_all_612_modes": boundary_phase_exact,
        "modal_reference": {
            "definition": base["dtn_modal_reference"],
            "top_z_nm": base["dtn_top_reference_z"],
            "bottom_z_nm": base["dtn_bottom_reference_z"],
            "amplitude_convention": base["dtn_amplitude_convention"],
            "boundary_phase_comparison": "per-mode boundary_phase exact equality; raw coefficient and boundary-phased amplitude differences both retained",
        },
        "modal_amplitude_comparisons_no_phase_fit": amp,
        "per_mode_power_differences": power_delta,
        "totals": metrics,
    }

summary = {
    "schema": "task40_d13_bxyz_same_coordinate_comparison_v1",
    "method": "same stored sample coordinates and ordered FE port mode keys; direct complex differences, no phase alignment; all comparisons use the original output artifacts",
    "scope_limit": "sampled points and finite active R13 rectangle only; not a full-domain FE norm and not FULL_DTN verification",
    "surface_quadrature": {
        "degree": base["surface_quadrature_degree"],
        "witness_status": base["surface_quadrature_witness_status"],
        "binding": "p6_condensed_direct_summary.production_port_mpc_witness.dtn_quadrature_degree",
    },
    "sample_plane_scope": {
        "interface_plane_indices": base["samples_meta"]["interface_plane_indices"],
        "z_nm": [
            base["samples_meta"]["plane_metrics"][i]["z_nm"]
            for i in base["samples_meta"]["interface_plane_indices"]
        ],
        "tangential_components": base["samples_meta"]["tangential_components"],
        "meaning": "horizontal interior modal-region planes, not pillar x/y sidewalls and not z=0/120 material interfaces",
    },
    "sidewall_artifact": {
        "path": "docs/task40para_phi90_mesh_modes_direct/outcomes/records/d13_bxyz_sidewall_comparison.json",
        "sha256": sha256_file(Path("docs/task40para_phi90_mesh_modes_direct/outcomes/records/d13_bxyz_sidewall_comparison.json")),
        "status": "SAVED_DG6_NODE_DIAGNOSTIC_NOT_CANONICAL_HCURL_TRACE_GATE",
        "method": "exact coordinates already present in saved VTU DG6 nodal field; no visualization interpolation or phase fit",
        "limitation": "within-run duplicate-cell trace spread is non-negligible; preserve as diagnostic, do not call the sidewall trace gate passed",
    },
    "correction_to_prior_status_message": "The earlier 2.36e-8 Y transmission figure was only the propagating subset. Across all 390 power-carrying channels the maximum |delta T| is separately reported below; lossy-bottom channels with propagating=false remain included.",
    "mode_identity": {"count": base["mode_count"], "sha256": base["mode_sha256"], "all_four_exact": all(c["mode_sha256"] == base["mode_sha256"] for c in cases.values())},
    "base_B": {k: v for k, v in base.items() if k not in ("modal_metrics", "modal_orders", "samples_meta", "samples")},
    "cases_XYZ": {k: {kk: vv for kk, vv in v.items() if kk not in ("modal_metrics", "modal_orders", "samples_meta", "samples")} for k, v in cases.items() if k != "B"},
    "comparisons_to_B": comparisons,
    "conclusion": {
        "R_change_y_is_over_1e-5": comparisons["Y"]["totals"]["R_total"]["absolute_delta"] > 1e-5,
        "sampled_complex_fields_are_a_diagnostic_not_a_full_norm": True,
        "full_dtn_status_preserved": "FULL_DTN_NOT_VERIFIED",
        "authority_status_preserved": "AUTHORITY_LIMITED",
        "sidewall_trace_gate": "NOT_MEASURED_AS_CANONICAL_HCURL",
        "next_mesh": "Y2: bisect every actual Y interval once; x/z unchanged from Y; preserve same 612-mode SHA and q28",
    },
}
output = Path("docs/task40para_phi90_mesh_modes_direct/outcomes/records/d13_bxyz_comparison.json")
output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps({"output": str(output), "bytes": output.stat().st_size, "sha256": sha256_file(output), "same_coordinates": {k: v["same_sample_coordinates_exactly"] for k, v in comparisons.items()}, "samples": {k: v["sample_field_comparisons_no_phase_fit"] for k, v in comparisons.items()}, "modes": {k: v["modal_amplitude_comparisons_no_phase_fit"] for k, v in comparisons.items()}, "power": {k: v["per_mode_power_differences"] for k, v in comparisons.items()}, "totals": {k: v["totals"] for k, v in comparisons.items()}}, indent=2, sort_keys=True))
