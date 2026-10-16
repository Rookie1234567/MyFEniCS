"""Offline comparison of saved D13 Y/Y2/Y3 fields before and after cutoff fix.

Reads each saved sample NPZ once. Does not load VTU, resource streams, FE
objects, or solver state. Complex comparisons use the stored values directly;
no phase fit or spatial interpolation is performed.
"""
from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[4]
RESULTS = REPO / "results/si_block_phi90_50x50_17x20_h120"
OUT = REPO / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
CSV_PATH = OUT / "d13_y_y2_y3_relative_cutoff_all_612_modes_v1.csv"
JSON_PATH = OUT / "d13_y_y2_y3_relative_cutoff_comparison_v1.json"

CASES = {
    "Y_legacy": (
        "task40_phi90_13p5_D13_Y_p6_direct_v1__full3d_direct__mpi1__Mna",
        "20261016T102453.831934Z",
        "9c0fe6a30554aab33a04ff0245b19c03e4f01f28",
        "legacy_absolute_floor_relative_v1",
    ),
    "Y2_legacy": (
        "task40_phi90_13p5_D13_Y2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "20261016T112452.011352Z",
        "74d5aae3dea064e128e53a253fc5aac0f2b1f146",
        "legacy_absolute_floor_relative_v1",
    ),
    "Y3_legacy": (
        "task40_phi90_13p5_D13_Y3_p6_direct_v1__full3d_direct__mpi1__Mna",
        "20261016T122621.622353Z",
        "d742562e706b896cdb78da7fe8ba9c3dfd83f4b0",
        "legacy_absolute_floor_relative_v1",
    ),
    "Y2_relative_only": (
        "task40_phi90_13p5_D13_Y2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "20261016T190312.893443Z",
        "73e2fd2c4a36c9698298235148c59aa1551d74d6",
        "scale_homogeneous_relative_only_v1",
    ),
}

SAMPLE_FIELDS = (
    "E_V_per_m",
    "H_A_per_m",
    "E_t_interface_V_per_m",
    "H_t_interface_A_per_m",
)
CSV_CASES = tuple(CASES)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(path: Path) -> tuple[Any, str]:
    data = path.read_bytes()
    return json.loads(data), _sha256(data)


def _array_sha256(array: np.ndarray) -> str:
    return _sha256(np.ascontiguousarray(array).view(np.uint8).tobytes())


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _complex(pair: list[float] | tuple[float, float]) -> complex:
    return complex(float(pair[0]), float(pair[1]))


def _pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _key(row: dict[str, Any]) -> tuple[str, int, int, str]:
    return (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"]))


def _norm_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    a = np.asarray(reference)
    b = np.asarray(candidate)
    delta = b - a
    norm_a = float(np.linalg.norm(a.ravel()))
    norm_b = float(np.linalg.norm(b.ravel()))
    norm_delta = float(np.linalg.norm(delta.ravel()))
    max_abs = float(np.max(np.abs(delta), initial=0.0))
    flat_index = int(np.argmax(np.abs(delta))) if delta.size else 0
    max_index = list(np.unravel_index(flat_index, delta.shape)) if delta.size else []
    return {
        "reference_l2": norm_a,
        "candidate_l2": norm_b,
        "delta_l2": norm_delta,
        "relative_l2_to_reference_no_phase_fit": norm_delta / norm_a if norm_a else None,
        "relative_l2_to_candidate_no_phase_fit": norm_delta / norm_b if norm_b else None,
        "max_abs_delta": max_abs,
        "max_delta_index": max_index,
    }


def _read_case(label: str, identity: tuple[str, str, str, str]) -> dict[str, Any]:
    directory, stamp, expected_source, cutoff_policy = identity
    run = RESULTS / directory / stamp
    output = run / "numerical_output"
    required = (
        run / "run_manifest.json",
        run / "run_summary.json",
        run / "workflow_phase.json",
        run / "p6_condensed_direct_summary.json",
        run / "source_sha.txt",
        run / "input_sha256.txt",
        run / "physical_model_sha256.txt",
        run / "resolved_config.json",
    )
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)

    manifest, manifest_sha = _json(run / "run_manifest.json")
    summary, _ = _json(run / "run_summary.json")
    phase, phase_sha = _json(run / "workflow_phase.json")
    direct, direct_sha = _json(run / "p6_condensed_direct_summary.json")
    power, power_sha = _json(output / "dtn_port_power_metrics_3d.json")
    volume, volume_sha = _json(output / "volume_absorption.json")
    modal, modal_sha = _json(output / "dtn_port_diffraction_orders_3d.json")
    auxiliary, auxiliary_sha = _json(output / "dtn_auxiliary_amplitudes_3d.json")
    samples_meta, samples_meta_sha = _json(output / "full3d_reference_samples.json")

    npz_path = output / "full3d_reference_samples.npz"
    npz_bytes = npz_path.read_bytes()
    if _sha256(npz_bytes) != samples_meta["archive_sha256"]:
        raise ValueError(f"{label}: sample NPZ hash does not match its saved metadata")
    with np.load(io.BytesIO(npz_bytes), allow_pickle=False) as archive:
        sample_arrays = {name: archive[name] for name in archive.files}

    source_sha = (run / "source_sha.txt").read_text().strip()
    if source_sha != expected_source:
        raise ValueError(f"{label}: source identity mismatch {source_sha} != {expected_source}")
    resource = summary["resource_authority"]
    if resource["classification"] != "COMPLETED" or not resource["descendants_cleared"]:
        raise ValueError(f"{label}: run is not a completed, cleared case")
    if len(modal["orders"]) != 612 or len(auxiliary) != 612:
        raise ValueError(f"{label}: expected 612 modal/auxiliary rows")
    if power["active_mode_sha256"] != "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e":
        raise ValueError(f"{label}: unexpected active mode identity")
    if direct["production_port_mpc_witness"]["dtn_quadrature_degree"] != 28:
        raise ValueError(f"{label}: unexpected surface quadrature")
    if not all(name in sample_arrays for name in (*SAMPLE_FIELDS, "x_nm", "y_nm", "z_nm")):
        raise ValueError(f"{label}: missing sample fields")

    by_aux = {int(row["auxiliary_index"]): row for row in auxiliary}
    if sorted(by_aux) != list(range(612)):
        raise ValueError(f"{label}: auxiliary indices are not a complete 0..611 mapping")
    modal_by_aux = {int(row["auxiliary_index"]): row for row in modal["orders"]}
    if sorted(modal_by_aux) != list(range(612)):
        raise ValueError(f"{label}: mode rows are not a complete auxiliary-index mapping")
    for index in range(612):
        if _key(by_aux[index]) != _key(modal_by_aux[index]):
            raise ValueError(f"{label}: auxiliary/modal key mismatch at index {index}")

    axes = direct["mesh_evidence"]["axis_sha256_le_f64"]
    axis_counts = direct["mesh_evidence"]["axis_cell_counts"]
    run_id = manifest.get("run_id", direct.get("run_id"))
    current_factor_evidence = direct.get("direct_factor_evidence", {})
    six_key_witness = current_factor_evidence.get("six_key_full_primal_witness", {})
    projection_comparison = six_key_witness.get("projection_comparison")
    source_policy = cutoff_policy
    if cutoff_policy == "legacy_absolute_floor_relative_v1":
        source_policy = {
            "effective_policy": "absolute_floor_relative_v1",
            "threshold": "max(1e-30, 1e-13 * global_maximum)",
            "evidence": f"source {source_sha} contains the three production max(1e-30, relative_tol*global_maximum) decisions",
            "recorded_in_run_manifest": False,
        }
    else:
        operator = direct["direct_factor_evidence"]["operator_identity"]
        if operator["dtn_sparse_cutoff_policy"] != cutoff_policy:
            raise ValueError(f"{label}: run operator cutoff identity mismatch")
        source_policy = {
            "effective_policy": cutoff_policy,
            "relative_tolerance": operator["dtn_sparse_cutoff_relative_tolerance"],
            "identity_sha256": operator["dtn_sparse_cutoff_identity_sha256"],
            "recorded_in_run_manifest": True,
        }

    case = {
        "label": label,
        "run_directory": str(run),
        "run_id": run_id,
        "source_sha": source_sha,
        "input_sha256": (run / "input_sha256.txt").read_text().strip(),
        "physical_model_sha256": (run / "physical_model_sha256.txt").read_text().strip(),
        "resolved_config_sha256": _sha256((run / "resolved_config.json").read_bytes()),
        "run_manifest_sha256": manifest_sha,
        "direct_summary_sha256": direct_sha,
        "workflow_phase_sha256": phase_sha,
        "classification": summary["result_classification"],
        "exit_status": summary["exit_status"],
        "phase": phase["phase"],
        "terminal_stage": phase["stage"],
        "operator_scope": direct["operator_scope"],
        "qualification_status": direct["status"],
        "full_dtn_status": direct["full_dtn_status"],
        "cutoff_policy": source_policy,
        "axis_cell_counts": axis_counts,
        "axis_sha256": axes,
        "active_mode_count": power["active_mode_count"],
        "active_mode_sha256": power["active_mode_sha256"],
        "surface_quadrature_degree": direct["production_port_mpc_witness"]["dtn_quadrature_degree"],
        "volume_quadrature_records": direct["operator_identity"]["volume_quadrature_records"],
        "port_reference": {
            "description": power["dtn_port_modal_reference"],
            "top_z_nm": power["dtn_port_top_reference_z"],
            "bottom_z_nm": power["dtn_port_bottom_reference_z"],
            "amplitude_convention": power["dtn_port_modal_amplitude_convention"],
        },
        "totals": {
            "R_total": power["R_total"],
            "R00_s": power["R00_s"],
            "R00_p": power["R00_p"],
            "R00_total": power["R00_s"] + power["R00_p"],
            "T_total": power["T_total"],
            "T00_s": modal_by_aux[next(i for i, r in modal_by_aux.items() if r["side"] == "bottom" and int(r["m"]) == 0 and int(r["n"]) == 0 and r["polarization"] == "s")]["T"],
            "T00_p": modal_by_aux[next(i for i, r in modal_by_aux.items() if r["side"] == "bottom" and int(r["m"]) == 0 and int(r["n"]) == 0 and r["polarization"] == "p")]["T"],
            "A_balance": power["A_balance"],
            "A_volume": volume["A_volume_total"],
            "A_grating": volume["A_grating"],
            "A_substrate": volume["A_substrate"],
            "energy_closure_abs": abs(1.0 - power["R_total"] - power["T_total"] - volume["A_volume_total"]),
        },
        "solver": {
            "condensed_relative": direct["residuals"]["condensed_direct_relative"],
            "original_A6_relative": direct["residuals"]["original_A6_active_rectangle_relative"],
            "same_factor_corrections": direct["factor"]["same_factor_correction_count"],
        },
        "legacy_six_key_raw_projection_audit": projection_comparison,
        "native_port_residual_observation": current_factor_evidence.get("native_port_residual_facts"),
        "resource": {
            "elapsed_seconds": resource["elapsed_seconds"],
            "rss_peak_bytes": resource["sampled_process_tree_rss_peak_bytes"],
            "swap_peak_bytes": resource["sampled_process_tree_swap_peak_bytes"],
            "pss_status": resource["pss_status"],
            "job_swap_activity": resource["job_swap_activity"],
        },
        "artifact_hashes": {
            "power_metrics_json_sha256": power_sha,
            "volume_absorption_json_sha256": volume_sha,
            "modal_orders_json_sha256": modal_sha,
            "auxiliary_json_sha256": auxiliary_sha,
            "samples_metadata_json_sha256": samples_meta_sha,
            "samples_npz_sha256_recorded_by_run": samples_meta["archive_sha256"],
        },
        "sample_metadata": {
            "point_count": samples_meta["point_count"],
            "array_shape_z_y_x_component": samples_meta["array_shape_z_y_x_component"],
            "interface_plane_indices": samples_meta["interface_plane_indices"],
            "plane_metrics": samples_meta["plane_metrics"],
            "interface_planes_are_horizontal_z_planes": True,
            "canonical_pillar_sidewall_gate": "NOT_MEASURED",
        },
        "modal_orders": modal["orders"],
        "auxiliary_rows": auxiliary,
        "samples": sample_arrays,
        "sample_coordinates": {axis: sample_arrays[f"{axis}_nm"] for axis in ("x", "y", "z")},
    }
    return case


def _mode_class_indices(rows: list[dict[str, Any]]) -> dict[str, list[int]]:
    return {
        "all_612": list(range(len(rows))),
        "propagating": [i for i, row in enumerate(rows) if bool(row["propagating"])],
        "power_carrying": [i for i, row in enumerate(rows) if bool(row["power_carrying"])],
        "evanescent_nonpropagating": [i for i, row in enumerate(rows) if not bool(row["propagating"])],
    }


def _top_delta(values: np.ndarray, rows: list[dict[str, Any]], count: int = 8) -> list[dict[str, Any]]:
    order = np.argsort(np.abs(values))[::-1][:count]
    return [
        {"key": list(_key(rows[int(i)])), "abs_delta": float(abs(values[int(i)]))}
        for i in order
    ]


def _modal_pair(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    rows_a = reference["modal_orders"]
    rows_b = candidate["modal_orders"]
    keys_a = [_key(row) for row in rows_a]
    keys_b = [_key(row) for row in rows_b]
    if keys_a != keys_b:
        raise ValueError(f"mode order mismatch: {reference['label']} vs {candidate['label']}")
    for a, b in zip(rows_a, rows_b, strict=True):
        for field in ("beta", "boundary_phase", "medium", "direction", "polarization"):
            if a[field] != b[field]:
                raise ValueError(f"mode branch/reference mismatch on {_key(a)} field {field}")

    amplitude = {}
    for field, phase_scaled in (
        ("outgoing_amplitude", False),
        ("outgoing_amplitude_at_boundary", True),
        ("auxiliary_amplitude_total_projection", False),
    ):
        left = np.asarray([_complex(row[field]) for row in rows_a], dtype=np.complex128)
        right = np.asarray([_complex(row[field]) for row in rows_b], dtype=np.complex128)
        amplitude[field] = {**_norm_metrics(left, right), "largest_absolute_differences": _top_delta(right - left, rows_a)}

    classes = _mode_class_indices(rows_a)
    powers: dict[str, Any] = {}
    for class_name, indices in classes.items():
        powers[class_name] = {"count": len(indices)}
        for value_name in ("R", "T"):
            delta = np.asarray(
                [float(rows_b[i][value_name]) - float(rows_a[i][value_name]) for i in indices],
                dtype=np.float64,
            )
            abs_delta = np.abs(delta)
            max_local = int(np.argmax(abs_delta)) if len(indices) else None
            powers[class_name][value_name] = {
                "max_abs_delta": float(abs_delta[max_local]) if max_local is not None else 0.0,
                "max_key": list(_key(rows_a[indices[max_local]])) if max_local is not None else None,
                "count_abs_delta_gt_1e-6": int(np.count_nonzero(abs_delta > 1.0e-6)),
                "l2_delta": float(np.linalg.norm(delta)),
                "top_8": _top_delta(delta, [rows_a[i] for i in indices]),
            }

    totals = {}
    for key in ("R_total", "R00_s", "R00_p", "R00_total", "T_total", "T00_s", "T00_p", "A_balance", "A_volume", "A_grating", "A_substrate", "energy_closure_abs"):
        left = float(reference["totals"][key])
        right = float(candidate["totals"][key])
        totals[key] = {"reference": left, "candidate": right, "absolute_delta": abs(right - left)}

    samples = {}
    for field in SAMPLE_FIELDS:
        left = reference["samples"][field]
        right = candidate["samples"][field]
        metrics = _norm_metrics(left, right)
        metrics["shape"] = list(left.shape)
        metrics["dtype"] = str(left.dtype)
        if left.ndim and left.shape[-1] <= 3:
            metrics["per_last_component"] = [
                _norm_metrics(left[..., c], right[..., c]) for c in range(left.shape[-1])
            ]
        samples[field] = metrics
    return {
        "reference": reference["label"],
        "candidate": candidate["label"],
        "mesh_axis_counts": {"reference": reference["axis_cell_counts"], "candidate": candidate["axis_cell_counts"]},
        "source_sha": {"reference": reference["source_sha"], "candidate": candidate["source_sha"]},
        "cutoff_policy": {"reference": reference["cutoff_policy"], "candidate": candidate["cutoff_policy"]},
        "comparison_scope": "saved modal and exact-coordinate samples; no phase fit/interpolation",
        "modal_amplitude_differences": amplitude,
        "per_mode_power_differences": powers,
        "global_observable_differences": totals,
        "same_coordinate_complex_field_differences": samples,
    }


def _alpha_recovery_audit(case: dict[str, Any]) -> tuple[dict[str, Any], np.ndarray]:
    evidence_path = Path(case["run_directory"]) / "numerical_output/task40_direct_factor_evidence/evidence.json"
    evidence, evidence_sha = _json(evidence_path)
    artifact = evidence["artifacts"]["retained_modal_alpha"]
    alpha_path = Path(artifact["path"])
    alpha_bytes = alpha_path.read_bytes()
    if _sha256(alpha_bytes) != artifact["sha256"]:
        raise ValueError("retained modal alpha artifact file hash mismatch")
    alpha = np.load(io.BytesIO(alpha_bytes), allow_pickle=False)
    alpha = np.asarray(alpha, dtype=np.complex128)
    alpha_content_sha = _array_sha256(alpha)
    if list(alpha.shape) != artifact["shape"] or alpha.shape != (612,):
        raise ValueError("retained modal alpha shape does not match evidence")

    records = case["modal_orders"]
    recovered_by_index = {
        int(row["auxiliary_index"]): _complex(row["auxiliary_amplitude_total_projection"])
        for row in case["auxiliary_rows"]
    }
    modal_by_index = {int(row["auxiliary_index"]): row for row in records}
    if sorted(recovered_by_index) != list(range(612)) or sorted(modal_by_index) != list(range(612)):
        raise ValueError("retained-alpha comparison requires complete auxiliary index map")
    recovered = np.asarray([recovered_by_index[i] for i in range(612)], dtype=np.complex128)
    phase = np.asarray([_complex(modal_by_index[i]["boundary_phase"]) for i in range(612)], dtype=np.complex128)
    raw_delta = alpha - recovered
    alpha_boundary = phase * alpha
    recovered_boundary = phase * recovered
    boundary_delta = alpha_boundary - recovered_boundary

    def norm_pair(a: np.ndarray, b: np.ndarray) -> dict[str, Any]:
        delta = a - b
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        nd = float(np.linalg.norm(delta))
        max_index = int(np.argmax(np.abs(delta)))
        return {
            "reference_l2": na,
            "candidate_l2": nb,
            "delta_l2": nd,
            "relative_to_reference": nd / na if na else None,
            "relative_to_candidate": nd / nb if nb else None,
            "max_abs_delta": float(np.max(np.abs(delta))),
            "max_key": list(_key(modal_by_index[max_index])),
        }

    phase_abs = np.abs(phase)
    phase_min_index = int(np.argmin(phase_abs))
    phase_max_index = int(np.argmax(phase_abs))
    aux_matches_modes = True
    for i in range(612):
        row = modal_by_index[i]
        incident = _complex(row["incident_projection"])
        outgoing_from_recovered = recovered[i] - incident if row["side"] == "top" else recovered[i]
        saved_outgoing_boundary = _complex(row["outgoing_amplitude_at_boundary"])
        if not np.isclose(phase[i] * outgoing_from_recovered, saved_outgoing_boundary, rtol=5e-14, atol=0.0):
            aux_matches_modes = False
            break

    top_keys = []
    for key in (("top", -4, 0, "p"), ("top", 4, 0, "p")):
        index = next(i for i, row in modal_by_index.items() if _key(row) == key)
        top_keys.append(
            {
                "key": list(key),
                "auxiliary_index": index,
                "normalization_h_if_saved_in_six_key_witness": next(
                    (
                        row.get("normalization_h")
                        for row in evidence["six_key_full_primal_witness"]["orders"]
                        if (row.get("side"), int(row.get("m", 0)), int(row.get("n", 0)), row.get("polarization")) == key
                    ),
                    None,
                ),
                "boundary_phase_P": _pair(phase[index]),
                "retained_alpha_raw": _pair(alpha[index]),
                "recovered_auxiliary_raw": _pair(recovered[index]),
                "raw_delta": _pair(raw_delta[index]),
                "retained_alpha_boundary_P_times_alpha": _pair(alpha_boundary[index]),
                "recovered_auxiliary_boundary_P_times_aux": _pair(recovered_boundary[index]),
                "boundary_delta": _pair(boundary_delta[index]),
                "saved_outgoing_boundary_amplitude": modal_by_index[index]["outgoing_amplitude_at_boundary"],
            }
        )
    detail = {
        "status": "observed comparison; not a solver gate",
        "retained_alpha_source": artifact["path"],
        "retained_alpha_file_sha256": artifact["sha256"],
        "retained_alpha_array_content_sha256": alpha_content_sha,
        "retained_alpha_shape": list(alpha.shape),
        "retained_alpha_rows_semantics": evidence["augmented_layout"]["native_facts_retained_alpha_semantics"],
        "auxiliary_recovery_source": "saved dtn_auxiliary_amplitudes_3d.json auxiliary_amplitude_total_projection",
        "per_mode_mapping": "auxiliary_index 0..611; matches modal output key at each index",
        "same_per_mode_boundary_phase_applied_to_both_vectors": True,
        "all_mode_saved_outgoing_boundary_consistent_with_recovered_aux_and_incident": aux_matches_modes,
        "raw_retained_vs_recovered": norm_pair(alpha, recovered),
        "boundary_P_scaled_retained_vs_recovered": norm_pair(alpha_boundary, recovered_boundary),
        "boundary_phase_abs_range": {
            "min": float(phase_abs[phase_min_index]),
            "min_key": list(_key(modal_by_index[phase_min_index])),
            "max": float(phase_abs[phase_max_index]),
            "max_key": list(_key(modal_by_index[phase_max_index])),
        },
        "top_pm4_n0_p": top_keys,
        "factor_evidence_json_sha256": evidence_sha,
        "limitation": "H is available only for the saved six-key witness; other mode H values are not reconstructed here. P-scaled boundary comparison is reported per mode for all 612 entries.",
    }
    return detail, alpha


def _write_modal_csv(cases: dict[str, dict[str, Any]], alpha: np.ndarray) -> str:
    first = cases["Y_legacy"]["modal_orders"]
    fields = [
        "auxiliary_index", "side", "m", "n", "polarization", "medium", "beta_re", "beta_im",
        "propagating", "power_carrying", "boundary_phase_re", "boundary_phase_im",
    ]
    for label in CSV_CASES:
        fields.extend(
            [
                f"{label}_outgoing_raw_re", f"{label}_outgoing_raw_im",
                f"{label}_outgoing_boundary_re", f"{label}_outgoing_boundary_im",
                f"{label}_recover_aux_raw_re", f"{label}_recover_aux_raw_im",
                f"{label}_recover_aux_boundary_re", f"{label}_recover_aux_boundary_im",
                f"{label}_R", f"{label}_T",
            ]
        )
    fields.extend(
        [
            "Y2_relative_only_retained_alpha_raw_re", "Y2_relative_only_retained_alpha_raw_im",
            "Y2_relative_only_retained_alpha_boundary_re", "Y2_relative_only_retained_alpha_boundary_im",
            "Y2_relative_only_alpha_minus_recover_raw_re", "Y2_relative_only_alpha_minus_recover_raw_im",
            "Y2_relative_only_alpha_minus_recover_boundary_re", "Y2_relative_only_alpha_minus_recover_boundary_im",
        ]
    )
    OUT.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for base_row in first:
            index = int(base_row["auxiliary_index"])
            row: dict[str, Any] = {
                "auxiliary_index": index,
                "side": base_row["side"], "m": int(base_row["m"]), "n": int(base_row["n"]),
                "polarization": base_row["polarization"], "medium": base_row["medium"],
                "beta_re": _complex(base_row["beta"]).real,
                "beta_im": _complex(base_row["beta"]).imag,
                "propagating": base_row["propagating"],
                "power_carrying": base_row.get("power_carrying", False),
                "boundary_phase_re": _complex(base_row["boundary_phase"]).real,
                "boundary_phase_im": _complex(base_row["boundary_phase"]).imag,
            }
            P = _complex(base_row["boundary_phase"])
            for label, case in cases.items():
                modal = next(r for r in case["modal_orders"] if int(r["auxiliary_index"]) == index)
                aux = next(r for r in case["auxiliary_rows"] if int(r["auxiliary_index"]) == index)
                raw = _complex(modal["outgoing_amplitude"])
                boundary = _complex(modal["outgoing_amplitude_at_boundary"])
                aux_raw = _complex(aux["auxiliary_amplitude_total_projection"])
                aux_boundary = P * aux_raw
                row.update(
                    {
                        f"{label}_outgoing_raw_re": raw.real,
                        f"{label}_outgoing_raw_im": raw.imag,
                        f"{label}_outgoing_boundary_re": boundary.real,
                        f"{label}_outgoing_boundary_im": boundary.imag,
                        f"{label}_recover_aux_raw_re": aux_raw.real,
                        f"{label}_recover_aux_raw_im": aux_raw.imag,
                        f"{label}_recover_aux_boundary_re": aux_boundary.real,
                        f"{label}_recover_aux_boundary_im": aux_boundary.imag,
                        f"{label}_R": float(modal["R"]),
                        f"{label}_T": float(modal["T"]),
                    }
                )
            alpha_value = alpha[index]
            recovered = _complex(
                next(r for r in cases["Y2_relative_only"]["auxiliary_rows"] if int(r["auxiliary_index"]) == index)[
                    "auxiliary_amplitude_total_projection"
                ]
            )
            delta = alpha_value - recovered
            row.update(
                {
                    "Y2_relative_only_retained_alpha_raw_re": alpha_value.real,
                    "Y2_relative_only_retained_alpha_raw_im": alpha_value.imag,
                    "Y2_relative_only_retained_alpha_boundary_re": (P * alpha_value).real,
                    "Y2_relative_only_retained_alpha_boundary_im": (P * alpha_value).imag,
                    "Y2_relative_only_alpha_minus_recover_raw_re": delta.real,
                    "Y2_relative_only_alpha_minus_recover_raw_im": delta.imag,
                    "Y2_relative_only_alpha_minus_recover_boundary_re": (P * delta).real,
                    "Y2_relative_only_alpha_minus_recover_boundary_im": (P * delta).imag,
                }
            )
            writer.writerow(row)
    return _sha256(CSV_PATH.read_bytes())


def main() -> None:
    cases = {name: _read_case(name, identity) for name, identity in CASES.items()}
    labels = list(cases)
    reference = cases[labels[0]]
    for label, case in cases.items():
        for axis in ("x", "y", "z"):
            reference_coords = reference["sample_coordinates"][axis]
            candidate_coords = case["sample_coordinates"][axis]
            if not np.array_equal(reference_coords, candidate_coords):
                raise ValueError(f"sample coordinates differ for {label} axis {axis}")
        reference_keys = [_key(row) for row in reference["modal_orders"]]
        if [_key(row) for row in case["modal_orders"]] != reference_keys:
            raise ValueError(f"ordered mode keys differ for {label}")
        for field in ("beta", "boundary_phase"):
            if [row[field] for row in case["modal_orders"]] != [row[field] for row in reference["modal_orders"]]:
                raise ValueError(f"mode branch / boundary phase differs for {label}: {field}")

    alpha_audit, alpha = _alpha_recovery_audit(cases["Y2_relative_only"])
    modal_csv_sha = _write_modal_csv(cases, alpha)
    comparisons: dict[str, Any] = {}
    for ref_name, candidate_name in itertools.combinations(labels, 2):
        ref = cases[ref_name]
        candidate = cases[candidate_name]
        if ref["axis_sha256"]["x"] != candidate["axis_sha256"]["x"] or ref["axis_sha256"]["z"] != candidate["axis_sha256"]["z"]:
            axes_changed = [axis for axis in ("x", "y", "z") if ref["axis_sha256"][axis] != candidate["axis_sha256"][axis]]
        else:
            axes_changed = [axis for axis in ("x", "y", "z") if ref["axis_sha256"][axis] != candidate["axis_sha256"][axis]]
        same_policy = ref["cutoff_policy"]["effective_policy"] == candidate["cutoff_policy"]["effective_policy"]
        same_mesh = ref["axis_sha256"] == candidate["axis_sha256"]
        if same_mesh and not same_policy:
            classification = "same_mesh_cutoff_policy_changed"
        elif not same_mesh and same_policy:
            classification = "mesh_changed_same_cutoff_policy"
        elif same_mesh and same_policy:
            classification = "same_mesh_same_policy"
        else:
            classification = "mesh_and_cutoff_policy_changed_mixed_comparison"
        result = _modal_pair(ref, candidate)
        result["classification"] = classification
        result["changed_axes"] = axes_changed
        comparisons[f"{ref_name}_to_{candidate_name}"] = result

    sample_coords = {}
    for axis in ("x", "y", "z"):
        values = reference["sample_coordinates"][axis]
        sample_coords[axis] = {"shape": list(values.shape), "dtype": str(values.dtype), "sha256": _array_sha256(values)}

    class_counts = {
        "all_612": 612,
        "propagating": sum(bool(row["propagating"]) for row in reference["modal_orders"]),
        "power_carrying": sum(bool(row.get("power_carrying", False)) for row in reference["modal_orders"]),
        "evanescent_nonpropagating": sum(not bool(row["propagating"]) for row in reference["modal_orders"]),
    }
    report = {
        "schema": "task40.d13.relative_cutoff_saved_output_comparison.v1",
        "scope": "offline comparison of existing Y, legacy Y2, Y3, and relative-only Y2 outputs; no FE/factor/resource stream/VTU read",
        "method": {
            "complex_modal_comparison": "all 612 ordered active mode records; exact common mode keys, beta and boundary phase; no phase fit",
            "power_comparison": "per-mode R/T retained for all 612; max/L2/count summaries for all, propagating, power-carrying, and nonpropagating subsets",
            "field_comparison": "saved complex samples at exactly equal coordinates; no phase fitting and no interpolation",
            "sample_npz_read_count_each_in_final_export_pass": 1,
            "sample_npz_access_note": "Two earlier export attempts had already loaded each permitted small NPZ once before failing at output permissions / JSON serialization; this final pass rereads each once to produce the saved comparison. No VTU or resources.jsonl was read.",
            "retained_alpha_access_note": "The small retained_modal_alpha.npy was likewise read in each of the two failed export attempts and once in the final pass; no larger recovered-storage coefficient payload was read.",
            "sampled_Ht_scope": "saved H_t_interface at horizontal z planes (indices 0 and 4, z=10 and 110 nm), not pillar sidewalls/canonical H(curl) trace",
            "canonical_sidewall_gate": "NOT_MEASURED",
            "modal_class_counts": class_counts,
        },
        "cutoff_policy_caveat": {
            "legacy_cases": ["Y_legacy", "Y2_legacy", "Y3_legacy"],
            "legacy_policy": "absolute_floor_relative_v1; max(1e-30, 1e-13*global_maximum)",
            "legacy_identity_evidence": "source-bound dtn_port_3d.py at each run SHA has all three production cutoff sites using the absolute floor; policy was not separately serialized into those old manifests",
            "relative_only_case": "Y2_relative_only",
            "relative_only_policy": "scale_homogeneous_relative_only_v1 with relative tolerance 1e-13",
            "interpretation": "Y/Y2/Y3 mesh trend uses the legacy policy; the new Y2 is a same-grid policy comparison against legacy Y2. Any cross-policy mesh comparison is mixed and is not a same-operator convergence certificate.",
        },
        "cases": {
            label: {key: value for key, value in case.items() if key not in ("modal_orders", "auxiliary_rows", "samples", "sample_coordinates")}
            for label, case in cases.items()
        },
        "pairwise_comparisons": comparisons,
        "retained_alpha_vs_recovered_auxiliary": alpha_audit,
        "sample_coordinate_identity": {
            "exactly_equal_across_all_four_cases": True,
            "coordinates": sample_coords,
            "sample_grid_metadata": reference["sample_metadata"],
        },
        "full_modal_csv": {
            "path": str(CSV_PATH.relative_to(REPO)),
            "rows_excluding_header": 612,
            "contains_all_four_cases_boundary_complex_amplitudes_and_per_mode_R_T": True,
            "contains_new_Y2_retained_alpha_and_recovered_auxiliary_raw_and_P_scaled": True,
            "sha256": modal_csv_sha,
        },
        "analysis_script": {
            "path": str(Path(__file__).resolve().relative_to(REPO)),
            "sha256": _sha256(Path(__file__).read_bytes()),
        },
        "limitations": [
            "All cases remain finite R13 operators; FULL_DTN_NOT_VERIFIED is retained.",
            "The new relative-only Y2 differs in sparse extraction policy from legacy Y/Y2/Y3; this is not an isolated mesh refinement comparison.",
            "Saved E/H arrays cover the specified common sample grid only, not the full field or canonical pillar sidewall trace.",
            "R/T classifications and power values are those stored by each run; no uncomputed modes are filled as zero beyond the 612-mode active rectangle.",
            "Legacy raw projection audit failures remain historical evidence and are not overwritten by the boundary-scaled alpha/recovery comparison.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False, default=_json_default) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(JSON_PATH), "csv": str(CSV_PATH), "json_sha256": _sha256(JSON_PATH.read_bytes()), "csv_sha256": modal_csv_sha, "cases": len(cases), "mode_rows": len(reference["modal_orders"]), "pairs": len(comparisons)}, sort_keys=True))


if __name__ == "__main__":
    main()
