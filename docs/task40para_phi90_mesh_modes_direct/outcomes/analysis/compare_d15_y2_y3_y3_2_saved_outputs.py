"""Offline comparison of the three saved D15 Y-axis cases; no FE or phase fit."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[4]
ANALYSIS = Path(__file__).resolve().parent
RECORDS = REPO / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
JSON_PATH_V1 = RECORDS / "d15_y2_y3_y3_2_saved_output_comparison_20261021_v1.json"
JSON_PATH_V2 = RECORDS / "d15_y2_y3_y3_2_saved_output_comparison_20261021_v2.json"
CSV_PATH = RECORDS / "d15_y2_y3_y3_2_all_612_modes_20261021_v1.csv"
HELPER_PATH = ANALYSIS / "compare_d13_same_policy_y2_y3.py"
MODE_SHA = "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
THRESHOLDS = {
    "global_total_abs": 1.0e-5,
    "every_mode_R_T_abs": 1.0e-6,
    "boundary_complex_relative_no_phase_fit": 1.0e-4,
    "same_coordinate_E_H_relative_no_phase_fit": 1.0e-4,
}
SPECS = {
    "Y2": {
        "directory": "task40_phi90_13p5_D15_Y2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261021T074209.212424Z",
        "source_sha": "ba26075e2a871db10a81efbceeb32b51d95ea96b",
        "input_sha256": "c15aee982d76abe7027d07f7c65f6e3acec0d7e924da84ec5273ba2039c164ae",
        "axis_counts": [6, 8, 6],
        "y_segment_counts": [2, 4, 2],
    },
    "Y3": {
        "directory": "task40_phi90_13p5_D15_Y3_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261021T081011.745578Z",
        "source_sha": "ba26075e2a871db10a81efbceeb32b51d95ea96b",
        "input_sha256": "bf27bd09cb2b01509b13d2da414919db8b14fd49842e632cfa932fb00baa5943",
        "axis_counts": [6, 10, 6],
        "y_segment_counts": [3, 4, 3],
    },
    "Y3_2": {
        "directory": "task40_phi90_13p5_D15_Y3_2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261021T084703.634131Z",
        "source_sha": "a0d67b7f7052d80eff4bd5c9488384a2cd5a9864",
        "input_sha256": "968f47485f8e14bfac81da30e711b0fd4963be8402139d7560315d823142b01c",
        "axis_counts": [6, 10, 6],
        "y_segment_counts": [2, 6, 2],
    },
}
PAIR_ORDER = (("Y2", "Y3"), ("Y2", "Y3_2"), ("Y3", "Y3_2"))
SAMPLE_FIELDS = (
    "E_V_per_m",
    "H_A_per_m",
    "E_t_interface_V_per_m",
    "H_t_interface_A_per_m",
)


def _load_helper():
    spec = importlib.util.spec_from_file_location("task40_d13_compare_helpers", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load comparison helpers from {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _allowed_resolved_differences(paths: list[str]) -> list[str]:
    prefixes = (
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
    unexpected = [
        path
        for path in paths
        if not any(path == allowed or path.startswith(allowed + ".") for allowed in prefixes)
    ]
    if unexpected:
        raise ValueError(f"unexpected resolved configuration differences: {unexpected}")
    return paths


def _load_samples(case: dict[str, Any], helper: Any) -> dict[str, Any]:
    path = Path(case["sample_npz_path_internal"])
    raw = path.read_bytes()
    digest = _sha(raw)
    if digest != case["sample_metadata"]["archive_sha256"]:
        raise ValueError(f"{case['label']}: sample archive SHA mismatch")
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        samples = {name: archive[name].copy() for name in archive.files}
    required = (*SAMPLE_FIELDS, "x_nm", "y_nm", "z_nm")
    if not all(name in samples for name in required):
        raise ValueError(f"{case['label']}: required field/sample arrays are missing")
    return {"samples": samples, "archive_sha256": digest, "archive_bytes": len(raw)}


def _pair_sample_metrics(reference: dict[str, Any], candidate: dict[str, Any], helper: Any) -> dict[str, Any]:
    a = reference["samples"]
    b = candidate["samples"]
    coordinate_identity = {}
    for axis in ("x_nm", "y_nm", "z_nm"):
        same = a[axis].shape == b[axis].shape and np.array_equal(a[axis], b[axis])
        coordinate_identity[axis] = {
            "exactly_equal": bool(same),
            "shape": list(a[axis].shape),
            "sha256": helper._array_sha(a[axis]),
        }
        if not same:
            raise ValueError(f"sample coordinate {axis} differs; no interpolation is allowed")
    metrics: dict[str, Any] = {}
    for field in SAMPLE_FIELDS:
        if a[field].shape != b[field].shape:
            raise ValueError(f"sample field shape differs for {field}")
        item = {
            "shape": list(a[field].shape),
            "dtype": str(a[field].dtype),
            **helper._norm_metrics(a[field], b[field]),
        }
        if a[field].ndim and a[field].shape[-1] == 3:
            item["per_component"] = [
                {
                    "component": component,
                    **helper._norm_metrics(a[field][..., index], b[field][..., index]),
                }
                for index, component in enumerate(("x", "y", "z"))
            ]
        metrics[field] = item
    return {"coordinates": coordinate_identity, "fields": metrics}


def _pair_result(reference: dict[str, Any], candidate: dict[str, Any], helper: Any) -> dict[str, Any]:
    mode = helper._mode_differences(reference, candidate)
    global_items = mode["global_observables"]
    global_gate_fields = ("R_total", "T_total", "A_balance", "A_volume")
    global_gate = {
        field: {
            "reference": global_items[field]["Y2"],
            "candidate": global_items[field]["Y3"],
            "absolute_delta": global_items[field]["absolute_delta"],
            "limit": THRESHOLDS["global_total_abs"],
            "pass": bool(global_items[field]["absolute_delta"] <= THRESHOLDS["global_total_abs"]),
        }
        for field in global_gate_fields
    }
    groups = mode["per_mode_power_differences"]
    all_mode = groups["all_612"]
    per_mode_gate = {
        "count": all_mode["count"],
        "max_abs_delta_R": all_mode["R"]["max_abs_delta"],
        "max_delta_R_key": all_mode["R"]["max_delta_key"],
        "max_abs_delta_T": all_mode["T"]["max_abs_delta"],
        "max_delta_T_key": all_mode["T"]["max_delta_key"],
        "limit": THRESHOLDS["every_mode_R_T_abs"],
        "pass_R": bool(all_mode["R"]["max_abs_delta"] <= THRESHOLDS["every_mode_R_T_abs"]),
        "pass_T": bool(all_mode["T"]["max_abs_delta"] <= THRESHOLDS["every_mode_R_T_abs"]),
    }
    amplitudes = mode["modal_amplitudes"]
    boundary = amplitudes["outgoing_amplitude_at_boundary"]
    boundary_gate = {
        "relative_l2_no_phase_fit": boundary["relative_l2_to_reference"],
        "max_abs_delta": boundary["max_abs_delta"],
        "max_delta_key": boundary["max_delta_key"],
        "limit": THRESHOLDS["boundary_complex_relative_no_phase_fit"],
        "pass": bool(boundary["relative_l2_to_reference"] is not None and boundary["relative_l2_to_reference"] <= THRESHOLDS["boundary_complex_relative_no_phase_fit"]),
    }
    sample = _pair_sample_metrics(reference, candidate, helper)
    fields = sample["fields"]
    field_gate = {
        name: {
            "relative_l2_no_phase_fit": fields[name]["relative_l2_to_reference"],
            "limit": THRESHOLDS["same_coordinate_E_H_relative_no_phase_fit"],
            "pass": bool(fields[name]["relative_l2_to_reference"] is not None and fields[name]["relative_l2_to_reference"] <= THRESHOLDS["same_coordinate_E_H_relative_no_phase_fit"]),
        }
        for name in ("E_V_per_m", "H_A_per_m")
    }
    gates_pass = (
        all(item["pass"] for item in global_gate.values())
        and per_mode_gate["pass_R"]
        and per_mode_gate["pass_T"]
        and boundary_gate["pass"]
        and all(item["pass"] for item in field_gate.values())
    )
    return {
        "reference": reference["label"],
        "candidate": candidate["label"],
        "scope": "all 612 ordered FE-port modes; saved same-coordinate samples only; no interpolation or phase fit",
        "global_observables": global_gate,
        "per_channel_R_T": {
            "all_612_gate": per_mode_gate,
            "all_mode_classes": {
                key: {
                    "count": value["count"],
                    "max_abs_delta_R": value["R"]["max_abs_delta"],
                    "max_delta_R_key": value["R"]["max_delta_key"],
                    "max_abs_delta_T": value["T"]["max_abs_delta"],
                    "max_delta_T_key": value["T"]["max_delta_key"],
                }
                for key, value in groups.items()
            },
        },
        "boundary_complex_gate": boundary_gate,
        "same_coordinate_E_H_gate": field_gate,
        "same_coordinate_fields_diagnostics": {
            key: value for key, value in fields.items() if key not in ("E_V_per_m", "H_A_per_m")
        },
        "modal_amplitude_metrics": amplitudes,
        "global_observable_deltas_all": {
            field: {
                "reference_case": reference["label"],
                "candidate_case": candidate["label"],
                "reference_value": value["Y2"],
                "candidate_value": value["Y3"],
                "delta_candidate_minus_reference": value["delta_Y3_minus_Y2"],
                "absolute_delta": value["absolute_delta"],
            }
            for field, value in global_items.items()
        },
        "sample_coordinate_identity": sample["coordinates"],
        "sample_archives": {
            reference["label"]: reference["sample_archive"],
            candidate["label"]: candidate["sample_archive"],
        },
        "all_three_gate_groups_pass": bool(gates_pass),
    }


def _write_csv(cases: dict[str, dict[str, Any]], helper: Any) -> str:
    fields = [
        "reference", "candidate", "auxiliary_index", "side", "direction", "m", "n", "polarization",
        "medium", "propagating", "power_carrying", "R_ref", "R_candidate", "delta_R", "T_ref",
        "T_candidate", "delta_T", "modal_power_ref", "modal_power_candidate", "power_ratio_ref",
        "power_ratio_candidate", "boundary_ref_re", "boundary_ref_im", "boundary_candidate_re",
        "boundary_candidate_im", "boundary_delta_abs", "aux_total_ref_re", "aux_total_ref_im",
        "aux_total_candidate_re", "aux_total_candidate_im", "aux_total_delta_abs",
    ]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for reference_name, candidate_name in PAIR_ORDER:
            reference = cases[reference_name]
            candidate = cases[candidate_name]
            for a, b in zip(reference["modal_orders"], candidate["modal_orders"], strict=True):
                key = helper._key(a)
                boundary_a = helper._complex(a["outgoing_amplitude_at_boundary"])
                boundary_b = helper._complex(b["outgoing_amplitude_at_boundary"])
                index = int(a["auxiliary_index"])
                aux_a = helper._complex(reference["auxiliary_rows"][index]["auxiliary_amplitude_total_projection"])
                aux_b = helper._complex(candidate["auxiliary_rows"][index]["auxiliary_amplitude_total_projection"])
                writer.writerow({
                    "reference": reference_name, "candidate": candidate_name, "auxiliary_index": index,
                    "side": key[0], "direction": key[1], "m": key[2], "n": key[3], "polarization": key[4],
                    "medium": a["medium"], "propagating": bool(a["propagating"]), "power_carrying": bool(a["power_carrying"]),
                    "R_ref": a["R"], "R_candidate": b["R"], "delta_R": b["R"] - a["R"],
                    "T_ref": a["T"], "T_candidate": b["T"], "delta_T": b["T"] - a["T"],
                    "modal_power_ref": a["modal_power_code_units"], "modal_power_candidate": b["modal_power_code_units"],
                    "power_ratio_ref": a["power_ratio"], "power_ratio_candidate": b["power_ratio"],
                    "boundary_ref_re": boundary_a.real, "boundary_ref_im": boundary_a.imag,
                    "boundary_candidate_re": boundary_b.real, "boundary_candidate_im": boundary_b.imag,
                    "boundary_delta_abs": abs(boundary_b - boundary_a),
                    "aux_total_ref_re": aux_a.real, "aux_total_ref_im": aux_a.imag,
                    "aux_total_candidate_re": aux_b.real, "aux_total_candidate_im": aux_b.imag,
                    "aux_total_delta_abs": abs(aux_b - aux_a),
                })
    return _sha(CSV_PATH.read_bytes())


def _metadata_only_correction() -> None:
    raw = JSON_PATH_V1.read_bytes()
    report = json.loads(raw)
    for pair_name, pair in report["pairwise_comparisons"].items():
        reference = pair["reference"]
        candidate = pair["candidate"]
        corrected = {}
        for field, value in pair["global_observable_deltas_all"].items():
            corrected[field] = {
                "reference_case": reference,
                "candidate_case": candidate,
                "reference_value": value["Y2"],
                "candidate_value": value["Y3"],
                "delta_candidate_minus_reference": value["delta_Y3_minus_Y2"],
                "absolute_delta": value["absolute_delta"],
            }
        pair["global_observable_deltas_all"] = corrected
    report["metadata_correction"] = {
        "scope": "field labels only; no values, gates, modes, samples, or calculations changed",
        "supersedes_path": str(JSON_PATH_V1.relative_to(REPO)),
        "supersedes_sha256": _sha(raw),
        "corrected_global_value_keys": [
            "reference_case", "candidate_case", "reference_value", "candidate_value",
            "delta_candidate_minus_reference", "absolute_delta",
        ],
        "numerical_data_recomputed": False,
        "corrected_by_script": str(Path(__file__).resolve().relative_to(REPO)),
        "correction_script_sha256": _sha(Path(__file__).read_bytes()),
    }
    JSON_PATH_V2.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False, default=json_default) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"json": str(JSON_PATH_V2.relative_to(REPO)), "json_sha256": _sha(JSON_PATH_V2.read_bytes()), "supersedes_sha256": _sha(raw)}, sort_keys=True))


def json_default(value: Any) -> Any:
    helper = _load_helper()
    return helper._json_default(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-only-correction-from-v1", action="store_true")
    args = parser.parse_args()
    if args.metadata_only_correction_from_v1:
        _metadata_only_correction()
        return
    helper = _load_helper()
    results = REPO / "results/si_block_phi90_50x50_17x20_h120"
    cases = {label: helper._load_case(label, spec) for label, spec in SPECS.items()}
    for label, case in cases.items():
        sample = _load_samples(case, helper)
        case["samples"] = sample["samples"]
        case["sample_archive"] = {key: value for key, value in sample.items() if key != "samples"}
        spec = SPECS[label]
        if case["mesh"]["axis_counts"] != spec["axis_counts"]:
            raise ValueError(f"{label}: actual axis counts differ from the named D15 case")
        if case["source_sha"] != spec["source_sha"] or case["input_sha256"] != spec["input_sha256"]:
            raise ValueError(f"{label}: source/input identity mismatch")
        if case["mode_sha256"] != MODE_SHA or case["mode_count"] != 612:
            raise ValueError(f"{label}: mode identity mismatch")

    labels = list(cases)
    identity_checks = {
        "mode_sha_equal": all(cases[name]["mode_sha256"] == MODE_SHA for name in labels),
        "same_cutoff_policy": len({cases[name]["cutoff_policy"] for name in labels}) == 1,
        "same_cutoff_identity": len({cases[name]["cutoff_identity_sha256"] for name in labels}) == 1,
        "same_surface_q": len({cases[name]["surface_quadrature_degree"] for name in labels}) == 1,
        "same_volume_quadrature_records": all(cases[labels[0]]["volume_quadrature_records"] == cases[name]["volume_quadrature_records"] for name in labels[1:]),
        "x_axis_sha_equal": len({cases[name]["mesh"]["axis_sha256_le_f64"]["x"] for name in labels}) == 1,
        "z_axis_sha_equal": len({cases[name]["mesh"]["axis_sha256_le_f64"]["z"] for name in labels}) == 1,
        "all_y_axis_sha_distinct": len({cases[name]["mesh"]["axis_sha256_le_f64"]["y"] for name in labels}) == len(labels),
        "y_segment_counts": {name: SPECS[name]["y_segment_counts"] for name in labels},
        "y3_2_is_same_cell_count_redistribution": cases["Y3"]["mesh"]["axis_counts"] == cases["Y3_2"]["mesh"]["axis_counts"],
        "resolved_differences_allowed": {},
        "source_difference_note": "Y3-2 source adds the explicit D15 Y3-2 planner/profile route and its tests; D15 numerical operator implementation is unchanged. All three runs use the same relative-only sparse cutoff, mode ordering, surface/volume quadrature, and direct-solve contract.",
    }
    if not all(identity_checks[key] for key in (
        "mode_sha_equal", "same_cutoff_policy", "same_cutoff_identity", "same_surface_q",
        "same_volume_quadrature_records", "x_axis_sha_equal", "z_axis_sha_equal", "all_y_axis_sha_distinct",
    )):
        raise ValueError(f"operator or axis identity mismatch: {identity_checks}")

    pair_reports = {}
    for ref_name, cand_name in PAIR_ORDER:
        ref, cand = cases[ref_name], cases[cand_name]
        paths = helper._resolved_diff_paths(ref["resolved_config_internal"], cand["resolved_config_internal"])
        identity_checks["resolved_differences_allowed"][f"{ref_name}_to_{cand_name}"] = _allowed_resolved_differences(paths)
        pair_reports[f"{ref_name}_to_{cand_name}"] = _pair_result(ref, cand, helper)

    csv_sha = _write_csv(cases, helper)
    report = {
        "schema": "task40.d15.y2_y3_y3_2.saved_output_comparison.v1",
        "scope": "offline comparison of existing D15 Y2, Y3, and Y3-2 successful runs; no FE/factor/VTU/resource stream read; each small NPZ sample archive loaded once",
        "thresholds": THRESHOLDS,
        "identity": identity_checks,
        "cases": {
            label: {
                key: value for key, value in case.items()
                if key not in ("modal_orders", "auxiliary_rows", "samples", "resolved_config_internal", "sample_npz_path_internal")
            }
            for label, case in cases.items()
        },
        "pairwise_comparisons": pair_reports,
        "limitations": [
            "All runs are finite R13 rectangles with FULL_DTN_NOT_VERIFIED; this comparison does not qualify omitted DtN channels or the continuum solution.",
            "The sample arrays cover their saved common points only, not the full field. Horizontal E_t/H_t samples are not canonical pillar sidewall traces; sidewall remains NOT_MEASURED.",
            "No phase fitting, interpolation, mesh/field reconstruction, or extra solver action was performed.",
            "Y2 is [6,8,6] with y segments 2/4/2; Y3 is [6,10,6] with y 3/4/3; Y3-2 is [6,10,6] with y 2/6/2. The earlier Y2-to-Y3 v1 metadata typo is preserved historically and corrected in the v2 record; it did not alter any numerical data.",
        ],
        "csv": {
            "path": str(CSV_PATH.relative_to(REPO)),
            "rows_excluding_header": 612 * len(PAIR_ORDER),
            "covers_all_612_modes_for_each_pair": True,
            "sha256": csv_sha,
        },
        "analysis_script": {"path": str(Path(__file__).resolve().relative_to(REPO)), "sha256": _sha(Path(__file__).read_bytes())},
    }
    RECORDS.mkdir(parents=True, exist_ok=True)
    JSON_PATH_V2.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False, default=helper._json_default) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(JSON_PATH_V2.relative_to(REPO)), "json_sha256": _sha(JSON_PATH_V2.read_bytes()), "csv": str(CSV_PATH.relative_to(REPO)), "csv_sha256": csv_sha, "pair_pass": {name: item["all_three_gate_groups_pass"] for name, item in pair_reports.items()}, "npz_reads_per_case": {label: 1 for label in labels}}, sort_keys=True))


if __name__ == "__main__":
    main()
