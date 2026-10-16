"""Compare saved Task40 D13 Y and Y2 outputs without phase fitting."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path("results/si_block_phi90_50x50_17x20_h120")
CASES = {
    "Y": ("task40_phi90_13p5_D13_Y_p6_direct_v1", "20261016T102453.831934Z"),
    "Y2": ("task40_phi90_13p5_D13_Y2_p6_direct_v1", "20261016T112452.011352Z"),
}
IDENTITY_FIELDS = (
    "side",
    "direction",
    "m",
    "n",
    "polarization",
    "medium",
    "alpha",
    "gamma",
    "beta",
    "kz",
    "vertical_sign",
    "propagating",
    "power_carrying",
    "refractive_index",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def array_sha256(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    return hashlib.sha256(contiguous.view(np.uint8)).hexdigest()


def norm_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict:
    delta = np.asarray(candidate) - np.asarray(reference)
    reference_norm = float(np.linalg.norm(np.asarray(reference).ravel()))
    delta_norm = float(np.linalg.norm(delta.ravel()))
    return {
        "reference_l2": reference_norm,
        "candidate_l2": float(np.linalg.norm(np.asarray(candidate).ravel())),
        "delta_l2": delta_norm,
        "relative_l2_no_phase_fit": (
            delta_norm / reference_norm
            if reference_norm
            else (0.0 if delta_norm == 0.0 else float("inf"))
        ),
        "max_abs_delta": float(np.max(np.abs(delta))),
    }


def complex_value(pair: list[float]) -> complex:
    return complex(float(pair[0]), float(pair[1]))


def mode_key(item: dict) -> tuple:
    return (
        item["side"],
        item["direction"],
        int(item["m"]),
        int(item["n"]),
        item["polarization"],
    )


def read_case(label: str) -> dict:
    run_name, stamp = CASES[label]
    run_dir = ROOT / f"{run_name}__full3d_direct__mpi1__Mna" / stamp
    output = run_dir / "numerical_output"
    run_summary = json.loads((run_dir / "run_summary.json").read_text())
    direct = json.loads((run_dir / "p6_condensed_direct_summary.json").read_text())
    power = json.loads((output / "dtn_port_power_metrics_3d.json").read_text())
    absorption = json.loads((output / "volume_absorption.json").read_text())
    samples_meta = json.loads((output / "full3d_reference_samples.json").read_text())
    modal = json.loads((output / "dtn_port_diffraction_orders_3d.json").read_text())
    with np.load(output / "full3d_reference_samples.npz", allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}

    resource = run_summary["resource_authority"]
    return {
        "label": label,
        "run_dir": str(run_dir),
        "source_sha": (run_dir / "source_sha.txt").read_text().strip(),
        "input_sha256": (run_dir / "input_sha256.txt").read_text().strip(),
        "physical_model_sha256": (run_dir / "physical_model_sha256.txt").read_text().strip(),
        "resolved_config_sha256": file_sha256(run_dir / "resolved_config.json"),
        "classification": run_summary["result_classification"],
        "exit_status": run_summary["exit_status"],
        "descendants_cleared": resource["resource_authority"]["descendants_cleared"]
        if "resource_authority" in resource
        else resource["descendants_cleared"],
        "elapsed_seconds": resource["elapsed_seconds"],
        "rss_peak_bytes": resource["sampled_process_tree_rss_peak_bytes"],
        "task_swap_peak_bytes": resource["sampled_process_tree_swap_peak_bytes"],
        "mode_count": power["active_mode_count"],
        "mode_sha256": power["active_mode_sha256"],
        "operator_scope": direct["operator_scope"],
        "full_dtn_status": direct["full_dtn_status"],
        "direct_passed": direct["passed"],
        "cells": direct["mesh_evidence"]["actual_global_cell_count"],
        "axis_counts": direct["mesh_evidence"]["axis_cell_counts"],
        "axis_sha256": direct["mesh_evidence"]["axis_sha256_le_f64"],
        "surface_q": direct["production_port_mpc_witness"]["dtn_quadrature_degree"],
        "volume_q_records": direct["operator_identity"].get("volume_quadrature_records"),
        "condensed_residual": direct["residuals"]["condensed_direct_relative"],
        "original_A6_relative": direct["residuals"]["original_A6_active_rectangle_relative"],
        "same_factor_corrections": direct["factor"]["same_factor_correction_count"],
        "R_total": power["R_total"],
        "R00_s": power["R00_s"],
        "R00_p": power["R00_p"],
        "T_total": power["T_total"],
        "A_balance": power["A_balance"],
        "A_volume": absorption["A_volume_total"],
        "A_grating": absorption["A_grating"],
        "A_substrate": absorption["A_substrate"],
        "energy_closure_abs": abs(
            1.0 - power["R_total"] - power["T_total"] - absorption["A_volume_total"]
        ),
        "modal_orders": modal["orders"],
        "power_metrics": power,
        "dtn_modal_reference": power["dtn_port_modal_reference"],
        "dtn_top_reference_z": power["dtn_port_top_reference_z"],
        "dtn_bottom_reference_z": power["dtn_port_bottom_reference_z"],
        "amplitude_convention": power["dtn_port_modal_amplitude_convention"],
        "samples_meta": samples_meta,
        "samples": arrays,
        "artifact_sha256": {
            "samples_npz": samples_meta["archive_sha256"],
            "samples_json": file_sha256(output / "full3d_reference_samples.json"),
            "power_metrics_json": file_sha256(output / "dtn_port_power_metrics_3d.json"),
            "volume_absorption_json": file_sha256(output / "volume_absorption.json"),
            "diffraction_orders_json": file_sha256(
                output / "dtn_port_diffraction_orders_3d.json"
            ),
        },
    }


def main() -> None:
    y = read_case("Y")
    y2 = read_case("Y2")
    keys = [mode_key(item) for item in y["modal_orders"]]
    y2_keys = [mode_key(item) for item in y2["modal_orders"]]
    if keys != y2_keys:
        raise SystemExit("ordered mode keys differ")
    branches_y = [{key: item[key] for key in IDENTITY_FIELDS} for item in y["modal_orders"]]
    branches_y2 = [{key: item[key] for key in IDENTITY_FIELDS} for item in y2["modal_orders"]]
    if branches_y != branches_y2:
        raise SystemExit("modal branch/material identity differs")
    boundary_phase_exact = all(
        left["boundary_phase"] == right["boundary_phase"]
        for left, right in zip(y["modal_orders"], y2["modal_orders"], strict=True)
    )
    port_convention_equal = (
        y["dtn_modal_reference"] == y2["dtn_modal_reference"]
        and y["dtn_top_reference_z"] == y2["dtn_top_reference_z"]
        and y["dtn_bottom_reference_z"] == y2["dtn_bottom_reference_z"]
        and y["amplitude_convention"] == y2["amplitude_convention"]
    )
    if not boundary_phase_exact or not port_convention_equal:
        raise SystemExit("port reference plane, amplitude convention, or per-mode boundary phase differs")

    coords = {}
    for name in ("x_nm", "y_nm", "z_nm"):
        a, b = y["samples"][name], y2["samples"][name]
        coords[name] = {
            "exact_array_equal": bool(np.array_equal(a, b)),
            "shape": list(a.shape),
            "Y_sha256": array_sha256(a),
            "Y2_sha256": array_sha256(b),
        }
    if not all(item["exact_array_equal"] for item in coords.values()):
        raise SystemExit("saved sample coordinates differ; do not compare interpolated fields")

    sample_comparisons = {}
    for name in (
        "E_V_per_m",
        "H_A_per_m",
        "E_t_interface_V_per_m",
        "H_t_interface_A_per_m",
    ):
        a, b = y["samples"][name], y2["samples"][name]
        sample_comparisons[name] = {
            "shape": list(a.shape),
            "dtype": str(a.dtype),
            **norm_metrics(a, b),
        }

    amplitudes = {}
    for field in (
        "outgoing_amplitude",
        "outgoing_amplitude_at_boundary",
        "auxiliary_amplitude_total_projection",
    ):
        a = np.asarray([complex_value(item[field]) for item in y["modal_orders"]])
        b = np.asarray([complex_value(item[field]) for item in y2["modal_orders"]])
        metrics = norm_metrics(a, b)
        differences = np.abs(b - a)
        top = np.argsort(differences)[-10:][::-1]
        metrics["largest_absolute_differences"] = [
            {"mode_key": list(keys[int(i)]), "abs_delta": float(differences[int(i)])}
            for i in top
        ]
        amplitudes[field] = metrics

    power_deltas = {}
    for class_name, predicate in (
        ("all_modes", lambda item: True),
        ("propagating", lambda item: bool(item["propagating"])),
        ("power_carrying", lambda item: bool(item["power_carrying"])),
    ):
        indices = [i for i, item in enumerate(y["modal_orders"]) if predicate(item)]
        class_result = {"count": len(indices)}
        for value_name in ("R", "T"):
            deltas = [
                abs(float(y2["modal_orders"][i][value_name]) - float(y["modal_orders"][i][value_name]))
                for i in indices
            ]
            pos = int(np.argmax(deltas)) if deltas else None
            class_result[value_name] = {
                "max_abs_delta": max(deltas, default=0.0),
                "mode_key": list(keys[indices[pos]]) if pos is not None else None,
                "count_over_1e-6": sum(value > 1e-6 for value in deltas),
            }
        power_deltas[class_name] = class_result

    totals = {}
    for name in (
        "R_total",
        "R00_s",
        "R00_p",
        "T_total",
        "A_balance",
        "A_volume",
        "A_grating",
        "A_substrate",
        "energy_closure_abs",
    ):
        totals[name] = {
            "Y": y[name],
            "Y2": y2[name],
            "absolute_delta": abs(y2[name] - y[name]),
        }

    y_meta = y["samples_meta"]
    y2_meta = y2["samples_meta"]
    horizontal_planes = {
        "Y": {
            "indices": y_meta["interface_plane_indices"],
            "z_nm": [y_meta["plane_metrics"][i]["z_nm"] for i in y_meta["interface_plane_indices"]],
            "tangential_components": y_meta["tangential_components"],
        },
        "Y2": {
            "indices": y2_meta["interface_plane_indices"],
            "z_nm": [y2_meta["plane_metrics"][i]["z_nm"] for i in y2_meta["interface_plane_indices"]],
            "tangential_components": y2_meta["tangential_components"],
        },
    }
    if horizontal_planes["Y"] != horizontal_planes["Y2"]:
        raise SystemExit("sample-plane or tangential-component metadata differs")

    sidewall_path = Path(
        "docs/task40para_phi90_mesh_modes_direct/outcomes/records/d13_bxyz_sidewall_comparison.json"
    )
    sidewall = json.loads(sidewall_path.read_text()) if sidewall_path.exists() else {}
    result = {
        "schema": "task40_d13_y_y2_same_coordinate_comparison_v1",
        "method": "saved complex samples and ordered FE port modes; direct differences, no phase fitting or interpolation",
        "scope_limit": "sampled values and finite active R13 rectangle only; not a full-domain norm and not full-DtN verification",
        "cases": {
            "Y": {k: v for k, v in y.items() if k not in ("modal_orders", "power_metrics", "samples_meta", "samples")},
            "Y2": {k: v for k, v in y2.items() if k not in ("modal_orders", "power_metrics", "samples_meta", "samples")},
        },
        "single_axis_identity": {
            "x_hash_equal": y["axis_sha256"]["x"] == y2["axis_sha256"]["x"],
            "z_hash_equal": y["axis_sha256"]["z"] == y2["axis_sha256"]["z"],
            "y_hash_changed": y["axis_sha256"]["y"] != y2["axis_sha256"]["y"],
            "Y_axis_counts": y["axis_counts"],
            "Y2_axis_counts": y2["axis_counts"],
            "Y2_cells": y2["cells"],
        },
        "mode_identity": {
            "count": y["mode_count"],
            "sha256": y["mode_sha256"],
            "ordered_keys_equal": True,
            "branch_and_material_identity_equal": True,
            "boundary_phase_exact_all_modes": boundary_phase_exact,
            "power_carrying_count": sum(bool(item["power_carrying"]) for item in y["modal_orders"]),
            "propagating_count": sum(bool(item["propagating"]) for item in y["modal_orders"]),
        },
        "port_reference_identity": {
            "exact": port_convention_equal,
            "dtn_modal_reference": y["dtn_modal_reference"],
            "top_reference_z_nm": y["dtn_top_reference_z"],
            "bottom_reference_z_nm": y["dtn_bottom_reference_z"],
            "amplitude_convention": y["amplitude_convention"],
            "boundary_phase_exact_all_modes": boundary_phase_exact,
            "raw_vs_boundary_note": "Raw outgoing coefficients and boundary-plane phased amplitudes are both retained. The raw coefficients include complex-beta reference-plane exponential scaling; physical port power is computed from the boundary-plane amplitude. The references and per-mode phase factors are identical between Y and Y2.",
        },
        "surface_quadrature": {
            "Y_degree": y["surface_q"],
            "Y2_degree": y2["surface_q"],
            "identity_binding": "production_port_mpc_witness.dtn_quadrature_degree in each run summary",
        },
        "sample_coordinates": coords,
        "sampled_complex_fields_no_phase_fit": sample_comparisons,
        "horizontal_reference_planes": {
            **horizontal_planes["Y"],
            "meaning": "horizontal modal-region planes, not pillar sidewalls or z=0/120 material interfaces",
        },
        "per_mode_amplitude_differences_no_phase_fit": amplitudes,
        "per_mode_power_differences": power_deltas,
        "totals": totals,
        "sidewall_canonical_trace_gate": {
            "status": "NOT_MEASURED_AS_CANONICAL_HCURL_TRACE_GATE",
            "prior_D13_BXYZ_diagnostic_status": sidewall.get("status"),
            "prior_D13_BXYZ_record": str(sidewall_path),
            "note": "The saved reference samples are horizontal planes. Existing DG6-node sidewall diagnostics showed non-negligible duplicate-cell trace spread and do not establish the canonical H(curl) sidewall trace gate; no new sidewall reconstruction is claimed here.",
        },
        "qualification": {
            "Y_authority": "AUTHORITY_LIMITED",
            "Y2_authority": "AUTHORITY_LIMITED",
            "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
            "conclusion": "Y-to-Y2 is a one-axis y-refinement comparison on fixed x/z/mode/q and saved sample coordinates. It does not establish full-domain convergence or canonical sidewall trace continuity.",
        },
    }
    output = Path("docs/task40para_phi90_mesh_modes_direct/outcomes/records/d13_y_y2_comparison.json")
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(output)
    print("Y2 comparison totals:")
    print(json.dumps({k: v for k, v in totals.items()}, indent=2, sort_keys=True))
    print("power maxima:")
    print(json.dumps(power_deltas, indent=2, sort_keys=True))
    print("sample fields:")
    print(json.dumps(sample_comparisons, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
