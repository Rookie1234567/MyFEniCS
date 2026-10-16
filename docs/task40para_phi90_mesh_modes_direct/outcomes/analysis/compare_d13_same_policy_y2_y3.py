"""Compare same-policy D13 Y2/Y3 saved outputs without FE or phase fitting."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import argparse
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[4]
RESULTS = REPO / "results/si_block_phi90_50x50_17x20_h120"
OUT = REPO / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
JSON_PATH = OUT / "d13_y2_y3_same_relative_only_comparison_v1.json"
CSV_PATH = OUT / "d13_y2_y3_same_relative_only_all_612_modes_v1.csv"
MODE_SHA = "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
CASES = {
    "Y2_relative_only": {
        "directory": "task40_phi90_13p5_D13_Y2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261016T190312.893443Z",
        "source_sha": "73e2fd2c4a36c9698298235148c59aa1551d74d6",
        "input_sha256": "7908141fe455ee73a1c8f213970a5c5655095a31f6afd10ce18904367b63a994",
        "axis_counts": [6, 24, 14],
    },
    "Y3_relative_only": {
        "directory": "task40_phi90_13p5_D13_Y3_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261016T202834.284773Z",
        "source_sha": "8faf8094e5309e7e7c0f0a094276cbacb31c1a00",
        "input_sha256": "0bcf87e01f6e17cc89808e0296cc24aafe8df3deb4f7265fe4c60b93e4ac6e22",
        "axis_counts": [6, 48, 14],
    },
}
SAMPLE_FIELDS = (
    "E_V_per_m",
    "H_A_per_m",
    "E_t_interface_V_per_m",
    "H_t_interface_A_per_m",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> tuple[Any, str]:
    data = path.read_bytes()
    return json.loads(data), _sha(data)


def _resolved_diff_paths(a: dict[str, Any], b: dict[str, Any], prefix: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        paths = []
        for key in sorted(set(a) | set(b)):
            child = f"{prefix}.{key}" if prefix else key
            if key not in a or key not in b:
                paths.append(child)
            else:
                paths.extend(_resolved_diff_paths(a[key], b[key], child))
        return paths
    if a == b:
        return []
    return [prefix]


def _array_sha(array: np.ndarray) -> str:
    return _sha(np.ascontiguousarray(array).view(np.uint8).tobytes())


def _complex(pair: list[float] | tuple[float, float]) -> complex:
    return complex(float(pair[0]), float(pair[1]))


def _pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _key(row: dict[str, Any]) -> tuple[str, str, int, int, str]:
    return (str(row["side"]), str(row["direction"]), int(row["m"]), int(row["n"]), str(row["polarization"]))


def _norm_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    a = np.asarray(reference)
    b = np.asarray(candidate)
    delta = b - a
    norm_a = float(np.linalg.norm(a.ravel()))
    norm_b = float(np.linalg.norm(b.ravel()))
    norm_delta = float(np.linalg.norm(delta.ravel()))
    max_index = int(np.argmax(np.abs(delta))) if delta.size else 0
    return {
        "reference_l2": norm_a,
        "candidate_l2": norm_b,
        "delta_l2": norm_delta,
        "relative_l2_to_reference": norm_delta / norm_a if norm_a else None,
        "relative_l2_to_candidate": norm_delta / norm_b if norm_b else None,
        "max_abs_delta": float(np.max(np.abs(delta), initial=0.0)),
        "max_delta_index": list(np.unravel_index(max_index, delta.shape)) if delta.size else [],
    }


def _load_case(label: str, spec: dict[str, Any]) -> dict[str, Any]:
    run = RESULTS / spec["directory"] / spec["stamp"]
    output = run / "numerical_output"
    run_summary, run_summary_sha = _read_json(run / "run_summary.json")
    manifest, manifest_sha = _read_json(run / "run_manifest.json")
    phase, phase_sha = _read_json(run / "workflow_phase.json")
    direct, direct_sha = _read_json(run / "p6_condensed_direct_summary.json")
    resolved_config, resolved_sha = _read_json(run / "resolved_config.json")
    power, power_sha = _read_json(output / "dtn_port_power_metrics_3d.json")
    volume, volume_sha = _read_json(output / "volume_absorption.json")
    modes, modes_sha = _read_json(output / "dtn_port_diffraction_orders_3d.json")
    auxiliary, auxiliary_sha = _read_json(output / "dtn_auxiliary_amplitudes_3d.json")
    sample_meta, sample_meta_sha = _read_json(output / "full3d_reference_samples.json")

    npz_path = output / "full3d_reference_samples.npz"
    if npz_path.stat().st_size != sample_meta["archive_bytes"]:
        raise ValueError(f"{label}: sample archive byte count differs from its metadata")

    resource = run_summary["resource_authority"]
    if run_summary["result_classification"] != "worker_exit0" or run_summary["exit_status"] != 0:
        raise ValueError(f"{label}: run did not exit successfully")
    if not resource["descendants_cleared"] or resource["remaining_child_pids"]:
        raise ValueError(f"{label}: process tree was not cleared")
    if not direct["passed"] or not direct["complete_solve"]:
        raise ValueError(f"{label}: direct solve summary did not pass")
    if power["active_mode_count"] != 612 or power["active_mode_sha256"] != MODE_SHA:
        raise ValueError(f"{label}: active mode inventory mismatch")
    if len(modes["orders"]) != 612 or len(auxiliary) != 612:
        raise ValueError(f"{label}: expected exactly 612 mode and auxiliary records")
    if [int(row["auxiliary_index"]) for row in modes["orders"]] != list(range(612)):
        raise ValueError(f"{label}: modal rows are not ordered by auxiliary index")
    if [int(row["auxiliary_index"]) for row in auxiliary] != list(range(612)):
        raise ValueError(f"{label}: auxiliary rows are not ordered by auxiliary index")
    if any(_key(a) != _key(b) for a, b in zip(modes["orders"], auxiliary, strict=True)):
        raise ValueError(f"{label}: modal and auxiliary mode identities differ")
    if power["output_scope"] != "ACTIVE_FE_DTN_PORTS":
        raise ValueError(f"{label}: unexpected output scope")
    if power["full_dtn_status"] != "FULL_DTN_NOT_VERIFIED":
        raise ValueError(f"{label}: full-DtN status changed")
    source_sha = (run / "source_sha.txt").read_text().strip()
    input_sha = (run / "input_sha256.txt").read_text().strip()
    physical_sha = (run / "physical_model_sha256.txt").read_text().strip()
    if source_sha != spec["source_sha"] or input_sha != spec["input_sha256"]:
        raise ValueError(f"{label}: source/input identity mismatch")
    operator = direct["direct_factor_evidence"]["operator_identity"]
    cutoff = operator["dtn_sparse_cutoff_policy"]
    if cutoff != "scale_homogeneous_relative_only_v1" or operator["dtn_sparse_cutoff_relative_tolerance"] != 1e-13:
        raise ValueError(f"{label}: cutoff policy is not the authorized relative-only policy")
    if direct["mesh_evidence"]["axis_cell_counts"] != spec["axis_counts"]:
        raise ValueError(f"{label}: mesh axis counts mismatch")
    if direct["production_port_mpc_witness"]["dtn_quadrature_degree"] != 28:
        raise ValueError(f"{label}: surface quadrature mismatch")
    return {
        "label": label,
        "run_directory": str(run),
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "resolved_config_internal": resolved_config,
        "run_manifest_sha256": manifest_sha,
        "workflow_phase_sha256": phase_sha,
        "run_summary_sha256": run_summary_sha,
        "classification": run_summary["result_classification"],
        "exit_status": run_summary["exit_status"],
        "terminal_stage": phase.get("stage"),
        "operator_scope": direct["operator_scope"],
        "qualification_status": direct["status"],
        "full_dtn_status": direct["full_dtn_status"],
        "mesh": {
            "axis_counts": direct["mesh_evidence"]["axis_cell_counts"],
            "actual_cells": direct["mesh_evidence"]["actual_global_cell_count"],
            "axis_sha256_le_f64": direct["mesh_evidence"]["axis_sha256_le_f64"],
        },
        "mode_count": power["active_mode_count"],
        "mode_sha256": power["active_mode_sha256"],
        "cutoff_policy": cutoff,
        "cutoff_relative_tolerance": operator["dtn_sparse_cutoff_relative_tolerance"],
        "cutoff_identity_sha256": operator["dtn_sparse_cutoff_identity_sha256"],
        "surface_quadrature_degree": direct["production_port_mpc_witness"]["dtn_quadrature_degree"],
        "volume_quadrature_records": direct["operator_identity"]["volume_quadrature_records"],
        "totals": {
            "R_total": power["R_total"],
            "R00_s": power["R00_s"],
            "R00_p": power["R00_p"],
            "R00_total": power["R00_s"] + power["R00_p"],
            "T_total": power["T_total"],
            "A_balance": power["A_balance"],
            "A_volume": volume["A_volume_total"],
            "A_grating": volume["A_grating"],
            "A_substrate": volume["A_substrate"],
            "energy_closure_abs": abs(1.0 - power["R_total"] - power["T_total"] - volume["A_volume_total"]),
            "reported_port_volume_closure_signed": volume.get("energy_closure_error_port_volume"),
        },
        "solver": {
            "condensed_relative": direct["residuals"]["condensed_direct_relative"],
            "condensed_gate": direct["residuals"]["condensed_direct_residual_gate"],
            "original_A6_relative": direct["residuals"]["original_A6_active_rectangle_relative"],
            "original_A6_gate": direct["residuals"]["original_A6_active_rectangle_relative_gate"],
            "same_factor_corrections": direct["factor"]["same_factor_correction_count"],
        },
        "resource": {
            "elapsed_seconds": resource["elapsed_seconds"],
            "tree_rss_peak_bytes": resource["sampled_process_tree_rss_peak_bytes"],
            "tree_swap_peak_bytes": resource["sampled_process_tree_swap_peak_bytes"],
            "pss_status": resource["pss_status"],
            "job_swap_activity": resource["job_swap_activity"],
            "global_swap_activity_unattributed": resource.get("global_swap_activity"),
        },
        "modal_orders": modes["orders"],
        "auxiliary_rows": auxiliary,
        "sample_metadata": sample_meta,
        "sample_npz_path_internal": str(npz_path),
        "artifact_hashes": {
            "power_metrics_json_sha256": power_sha,
            "volume_absorption_json_sha256": volume_sha,
            "diffraction_orders_json_sha256": modes_sha,
            "auxiliary_json_sha256": auxiliary_sha,
            "samples_metadata_json_sha256": sample_meta_sha,
            "samples_npz_sha256_recorded_by_metadata": sample_meta["archive_sha256"],
            "run_manifest_sha256": manifest_sha,
        },
    }


def _mode_differences(y2: dict[str, Any], y3: dict[str, Any]) -> dict[str, Any]:
    rows_a, rows_b = y2["modal_orders"], y3["modal_orders"]
    keys_a, keys_b = [_key(row) for row in rows_a], [_key(row) for row in rows_b]
    if keys_a != keys_b:
        raise ValueError("Y2/Y3 mode ordering differs")
    identity_fields = ("medium", "direction", "polarization", "beta", "boundary_phase", "propagating", "power_carrying", "refractive_index")
    for index, (a, b) in enumerate(zip(rows_a, rows_b, strict=True)):
        if any(a[field] != b[field] for field in identity_fields):
            raise ValueError(f"mode branch/reference identity differs at index {index}")

    complex_fields = ("outgoing_amplitude", "outgoing_amplitude_at_boundary", "auxiliary_amplitude_total_projection")
    amplitudes: dict[str, Any] = {}
    for field in complex_fields:
        a = np.asarray([_complex(row[field]) for row in rows_a], dtype=np.complex128)
        b = np.asarray([_complex(row[field]) for row in rows_b], dtype=np.complex128)
        diff = b - a
        index = int(np.argmax(np.abs(diff)))
        amplitudes[field] = {
            **_norm_metrics(a, b),
            "max_delta_key": list(keys_a[index]),
            "top_10_absolute_deltas": [
                {"key": list(keys_a[int(i)]), "abs_delta": float(abs(diff[int(i)]))}
                for i in np.argsort(np.abs(diff))[::-1][:10]
            ],
        }

    classes = {
        "all_612": np.ones(612, dtype=bool),
        "propagating": np.asarray([bool(row["propagating"]) for row in rows_a]),
        "power_carrying": np.asarray([bool(row["power_carrying"]) for row in rows_a]),
        "evanescent_nonpropagating": np.asarray([not bool(row["propagating"]) for row in rows_a]),
        "non_power_carrying": np.asarray([not bool(row["power_carrying"]) for row in rows_a]),
    }
    powers: dict[str, Any] = {}
    for class_name, mask in classes.items():
        indices = np.flatnonzero(mask)
        powers[class_name] = {"count": int(indices.size)}
        for field in ("R", "T", "modal_power_code_units", "power_ratio"):
            a = np.asarray([float(rows_a[int(i)][field]) for i in indices])
            b = np.asarray([float(rows_b[int(i)][field]) for i in indices])
            diff = b - a
            local = int(np.argmax(np.abs(diff))) if diff.size else 0
            powers[class_name][field] = {
                "delta_l2": float(np.linalg.norm(diff)),
                "max_abs_delta": float(np.max(np.abs(diff), initial=0.0)),
                "max_delta_key": list(keys_a[int(indices[local])]) if diff.size else None,
                "nonzero_delta_count": int(np.count_nonzero(diff)),
            }
    totals: dict[str, Any] = {}
    for field in y2["totals"]:
        if field.endswith("signed"):
            a = float(y2["totals"][field]); b = float(y3["totals"][field])
        else:
            a = float(y2["totals"][field]); b = float(y3["totals"][field])
        totals[field] = {"Y2": a, "Y3": b, "delta_Y3_minus_Y2": b - a, "absolute_delta": abs(b - a)}
    return {"all_612_mode_identity_exact_and_ordered": True, "modal_amplitudes": amplitudes, "per_mode_power_differences": powers, "global_observables": totals}


def _write_csv(y2: dict[str, Any], y3: dict[str, Any]) -> str:
    fields = [
        "auxiliary_index", "side", "direction", "m", "n", "polarization", "medium",
        "propagating", "power_carrying", "beta_re", "beta_im", "boundary_phase_re", "boundary_phase_im",
    ]
    for label in ("Y2", "Y3"):
        for prefix in ("raw_outgoing", "boundary_outgoing", "auxiliary_total_projection"):
            fields += [f"{label}_{prefix}_re", f"{label}_{prefix}_im"]
        fields += [f"{label}_modal_power_code_units", f"{label}_power_ratio", f"{label}_R", f"{label}_T"]
    fields += ["delta_boundary_outgoing_abs", "delta_modal_power_code_units", "delta_R", "delta_T"]
    OUT.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for a, b in zip(y2["modal_orders"], y3["modal_orders"], strict=True):
            row: dict[str, Any] = {
                "auxiliary_index": int(a["auxiliary_index"]), "side": a["side"], "direction": a["direction"],
                "m": int(a["m"]), "n": int(a["n"]), "polarization": a["polarization"], "medium": a["medium"],
                "propagating": bool(a["propagating"]), "power_carrying": bool(a["power_carrying"]),
                "beta_re": _complex(a["beta"]).real, "beta_im": _complex(a["beta"]).imag,
                "boundary_phase_re": _complex(a["boundary_phase"]).real, "boundary_phase_im": _complex(a["boundary_phase"]).imag,
            }
            for label, modal, aux in (("Y2", a, y2["auxiliary_rows"]), ("Y3", b, y3["auxiliary_rows"])):
                index = int(modal["auxiliary_index"])
                aux_row = aux[index]
                for prefix, field in (("raw_outgoing", "outgoing_amplitude"), ("boundary_outgoing", "outgoing_amplitude_at_boundary"), ("auxiliary_total_projection", "auxiliary_amplitude_total_projection")):
                    z = _complex(modal[field] if field != "auxiliary_amplitude_total_projection" else aux_row[field])
                    row[f"{label}_{prefix}_re"], row[f"{label}_{prefix}_im"] = z.real, z.imag
                row[f"{label}_modal_power_code_units"] = float(modal["modal_power_code_units"])
                row[f"{label}_power_ratio"] = float(modal["power_ratio"])
                row[f"{label}_R"] = float(modal["R"])
                row[f"{label}_T"] = float(modal["T"])
            zb = _complex(b["outgoing_amplitude_at_boundary"]) - _complex(a["outgoing_amplitude_at_boundary"])
            row["delta_boundary_outgoing_abs"] = abs(zb)
            row["delta_modal_power_code_units"] = float(b["modal_power_code_units"]) - float(a["modal_power_code_units"])
            row["delta_R"] = float(b["R"]) - float(a["R"])
            row["delta_T"] = float(b["T"]) - float(a["T"])
            writer.writerow(row)
    return _sha(CSV_PATH.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-only", action="store_true", help="validate run/mode/operator identity without reading sample NPZ archives")
    args = parser.parse_args()
    cases = {name: _load_case(name, spec) for name, spec in CASES.items()}
    y2, y3 = cases["Y2_relative_only"], cases["Y3_relative_only"]
    resolved_diffs = _resolved_diff_paths(y2["resolved_config_internal"], y3["resolved_config_internal"])
    allowed_diff_prefixes = (
        "derived.mesh_cells",
        "derived.native_capacity_profile",
        "discretization.mesh_axis_cell_counts",
        "discretization.mesh_axis_y_values",
        "discretization.mesh_plan_id",
        "discretization.mesh_plan_sha256",
        "provenance.expected_output_parent",
        "provenance.input_sha256",
        "provenance.physical_model_sha256",
        "provenance.source_path",
        "run_id",
        "solver.native_capacity_profile",
    )
    unexpected_resolved_diffs = [
        path for path in resolved_diffs
        if not any(path == allowed or path.startswith(allowed + ".") for allowed in allowed_diff_prefixes)
    ]
    if unexpected_resolved_diffs:
        raise ValueError(f"unexpected non-mesh resolved differences: {unexpected_resolved_diffs}")
    if y2["mode_sha256"] != y3["mode_sha256"] or y2["mode_count"] != y3["mode_count"]:
        raise ValueError("active mode identity differs")
    if y2["cutoff_policy"] != y3["cutoff_policy"] or y2["cutoff_relative_tolerance"] != y3["cutoff_relative_tolerance"]:
        raise ValueError("sparse cutoff policy differs")
    if y2["cutoff_identity_sha256"] != y3["cutoff_identity_sha256"]:
        raise ValueError("sparse cutoff identity differs")
    if y2["surface_quadrature_degree"] != y3["surface_quadrature_degree"]:
        raise ValueError("surface quadrature differs")
    if y2["volume_quadrature_records"] != y3["volume_quadrature_records"]:
        raise ValueError("volume quadrature differs")
    if y2["mesh"]["axis_sha256_le_f64"]["x"] != y3["mesh"]["axis_sha256_le_f64"]["x"] or y2["mesh"]["axis_sha256_le_f64"]["z"] != y3["mesh"]["axis_sha256_le_f64"]["z"]:
        raise ValueError("comparison expects only the y axis to change")
    if y2["mesh"]["axis_sha256_le_f64"]["y"] == y3["mesh"]["axis_sha256_le_f64"]["y"]:
        raise ValueError("expected distinct Y2/Y3 y axes")
    if args.metadata_only:
        print(json.dumps({"metadata_identity_preflight": "PASS", "physical_model_sha256_equal": y2["physical_model_sha256"] == y3["physical_model_sha256"], "physical_model_sha256": {"Y2": y2["physical_model_sha256"], "Y3": y3["physical_model_sha256"]}, "allowed_resolved_diff_paths": resolved_diffs, "cutoff_identity_sha256": y2["cutoff_identity_sha256"], "mode_sha256": y2["mode_sha256"], "surface_q": y2["surface_quadrature_degree"], "volume_q_records_equal": y2["volume_quadrature_records"] == y3["volume_quadrature_records"]}, sort_keys=True))
        return
    for case in cases.values():
        npz_bytes = Path(case["sample_npz_path_internal"]).read_bytes()
        actual_npz_sha = _sha(npz_bytes)
        if actual_npz_sha != case["sample_metadata"]["archive_sha256"]:
            raise ValueError(f"{case['label']}: sample archive hash differs from its metadata")
        with np.load(io.BytesIO(npz_bytes), allow_pickle=False) as archive:
            case["samples"] = {name: archive[name].copy() for name in archive.files}
        if len(case["samples"]["x_nm"]) == 0 or not all(name in case["samples"] for name in (*SAMPLE_FIELDS, "x_nm", "y_nm", "z_nm")):
            raise ValueError(f"{case['label']}: saved common sample arrays are incomplete")
        case["artifact_hashes"]["samples_npz_sha256"] = actual_npz_sha
    for axis in ("x_nm", "y_nm", "z_nm"):
        if not np.array_equal(y2["samples"][axis], y3["samples"][axis]):
            raise ValueError(f"saved sample coordinate {axis} differs; no interpolation is allowed")
    sample_metrics = {}
    for field in SAMPLE_FIELDS:
        a, b = y2["samples"][field], y3["samples"][field]
        item = {"shape": list(a.shape), "dtype": str(a.dtype), **_norm_metrics(a, b)}
        if a.ndim and a.shape[-1] == 3:
            item["per_component"] = [{"component": name, **_norm_metrics(a[..., i], b[..., i])} for i, name in enumerate(("x", "y", "z"))]
        sample_metrics[field] = item

    comparison = _mode_differences(y2, y3)
    csv_sha = _write_csv(y2, y3)
    sample_coords = {
        axis: {"shape": list(y2["samples"][axis].shape), "dtype": str(y2["samples"][axis].dtype), "sha256": _array_sha(y2["samples"][axis])}
        for axis in ("x_nm", "y_nm", "z_nm")
    }
    report = {
        "schema": "task40.d13.same_relative_only_y2_y3_saved_output_comparison.v1",
        "scope": "offline comparison of existing same-policy Y2 and Y3 terminal outputs; no FE/factor/VTU/resource stream read",
        "method": {
            "modal_scope": "all 612 ordered active FE port modes; compare complex coefficients on the same physical port reference plane",
            "power_scope": "every mode R/T/modal power across all 612; class summaries retained without dropping nonpropagating/evanescent channels",
            "field_scope": "saved complex E/H and tangential components on exact common sample coordinates; no interpolation or global phase fit",
            "sample_archive_reads": {label: 4 for label in cases},
            "sample_archive_read_note": "Three comparison invocations loaded each permitted small NPZ before writing the final JSON: the first stopped at a stale residual-key lookup, the second at an over-strict physical SHA equality assumption, and the third at JSON serialization of a NumPy scalar after computing the CSV. The fourth corrected pass writes the final JSON. Total reads in this comparison preparation: four per archive; no VTU or resource stream was read.",
            "canonical_sidewall_gate": "NOT_MEASURED; saved H_t is on horizontal z=10/110 nm planes and is not a pillar sidewall trace",
            "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
        },
        "same_operator_checks": {
            "physical_model_sha256_equal": y2["physical_model_sha256"] == y3["physical_model_sha256"],
            "physical_model_sha256": {"Y2": y2["physical_model_sha256"], "Y3": y3["physical_model_sha256"]},
            "resolved_diff_paths": resolved_diffs,
            "resolved_diff_interpretation": "The physical-model SHA differs because the resolved identity includes the y discretization and Task40 Y2/Y3 profile/run provenance; the only resolved paths that differ are those listed here. Geometry/material/incident/boundary settings outside these mesh/profile/provenance identities match.",
            "physical_model_sha256": {"Y2": y2["physical_model_sha256"], "Y3": y3["physical_model_sha256"]},
            "resolved_diff_paths": resolved_diffs,
            "resolved_diff_interpretation": "The physical-model SHA differs because the resolved identity includes the y discretization and Task40 Y2/Y3 profile/run provenance; the only resolved paths that differ are those listed here. Geometry/material/incident/boundary settings outside these mesh/profile/provenance identities match.",
            "active_mode_count": 612,
            "active_mode_sha256": MODE_SHA,
            "sparse_cutoff_policy": "scale_homogeneous_relative_only_v1",
            "sparse_cutoff_relative_tolerance": 1e-13,
            "sparse_cutoff_identity_sha256": y2["cutoff_identity_sha256"],
            "surface_quadrature_degree": 28,
            "volume_quadrature_records_equal": True,
            "x_axis_sha256_equal": True,
            "z_axis_sha256_equal": True,
            "y_axis_changed_only": True,
            "changed_y_cell_counts": [24, 48],
            "operator_scope_note": "Both are finite R13 rectangles with identical 612 mode order, cutoff and quadrature; this isolates the saved y-grid refinement under that finite operator, not full-DtN/continuum qualification.",
        },
        "cases": {label: {key: value for key, value in case.items() if key not in ("modal_orders", "auxiliary_rows", "samples", "resolved_config_internal", "sample_npz_path_internal")} for label, case in cases.items()},
        "global_observable_comparison": comparison["global_observables"],
        "modal_comparison": comparison,
        "same_coordinate_complex_field_comparison": sample_metrics,
        "sample_coordinate_identity": {"exactly_equal": True, "coordinates": sample_coords, "sample_grid_metadata": y2["sample_metadata"]},
        "resource_and_solver_comparison": {
            label: {"elapsed_seconds": case["resource"]["elapsed_seconds"], "tree_rss_peak_bytes": case["resource"]["tree_rss_peak_bytes"], "tree_swap_peak_bytes": case["resource"]["tree_swap_peak_bytes"], "solver": case["solver"], "qualification_status": case["qualification_status"], "full_dtn_status": case["full_dtn_status"]}
            for label, case in cases.items()
        },
        "csv": {"path": str(CSV_PATH.relative_to(REPO)), "rows_excluding_header": 612, "contains_all_mode_keys_complex_raw_and_boundary_amplitudes_per_mode_R_T_and_power": True, "sha256": csv_sha},
        "analysis_script": {"path": str(Path(__file__).resolve().relative_to(REPO)), "sha256": _sha(Path(__file__).read_bytes())},
        "limitations": [
            "Both outcomes are AUTHORITY_LIMITED finite-R13 results; this comparison does not verify omitted DtN channels.",
            "The sample arrays cover only their declared common points, not the full field. E_t/H_t and H_t are horizontal z-plane samples, not canonical pillar sidewall traces.",
            "No phase fitting, interpolation, mesh/field reconstruction, or additional solver action was performed.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False, default=_json_default) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(JSON_PATH), "json_sha256": _sha(JSON_PATH.read_bytes()), "csv": str(CSV_PATH), "csv_sha256": csv_sha, "cases": list(cases), "mode_rows": 612}, sort_keys=True))


if __name__ == "__main__":
    main()
