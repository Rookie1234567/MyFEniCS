#!/usr/bin/env python3
"""Compare D15-B, D15-Z1, and reused H15-B-as-D15-Z2 outputs offline.

Reads only compact terminal/stage/manifests, the 612-mode JSONs, volume/power
JSONs, and one small saved reference-sample NPZ per run. No VTU, resource stream,
mesh construction, FE assembly, factorization, or solve is performed.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
MODEL = "si_block_phi90_50x50_17x20_h120"
RESULTS = ROOT / "results" / MODEL
RECORDS = ROOT / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
RUNS = {
    "D15-B": "task40_phi90_13p5_D15_B_p6_direct_v1__full3d_direct__mpi1__Mna/20261021T063110.066502Z",
    "D15-Z1": "task40_phi90_13p5_D15_Z1_p6_direct_v1__full3d_direct__mpi1__Mna/20261021T224847.378522Z",
    # Role mapping only; preserve the historical H15-B identity and source.
    "D15-Z2-reused-H15-B": "task40_phi90_13p5_H15_B_p6_direct_v1__full3d_direct__mpi1__Mna/20261017T052011.288309Z",
}
EXPECTED = {
    "D15-B": {
        "run_id": "task40_phi90_13p5_D15_B_p6_direct_v1",
        "source_sha": "ba26075e2a871db10a81efbceeb32b51d95ea96b",
        "input_sha256": "57279867d909089baecda99b9802162439542ed56c683759945c90663c46faad",
        "physical_model_sha256": "6f78cddfd5bcc0082e20a975be283ca2f1f38ce800b6c52b74cd630baacc85e1",
        "resolved_config_sha256": "482a3655510d6730f2d6864e5afd1a9d0f6767b0d8f7fbd6009e024a10ddfa55",
        "axis_counts": [6, 4, 6],
        "axis_sha256": {
            "x": "bb1d6be1e2cec153c7bd67a71e29f5967b3035b4928cd06f51ee2c0b6f2a5361",
            "y": "c0a1052034574ddda40b805390f8debb6abd3da6ec558cc0458820ee941198ba",
            "z": "daf722948a31d19757622ba67544eeea6d49fdc2e433b979df9c11b2b450afb6",
        },
    },
    "D15-Z1": {
        "run_id": "task40_phi90_13p5_D15_Z1_p6_direct_v1",
        "source_sha": "4e8b8f3b1c9927b2e54fa9b7dac955680982136a",
        "input_sha256": "244a79ab009d6a8e5a4ea3cffb5e797a91c51634cc329eae045f695bee5bd4dc",
        "physical_model_sha256": "a820e4c34e5b36efde5b978e331a1a3ccf71d5cff999e189d8d1e8d1cc4490e8",
        "resolved_config_sha256": "b4e4e56fa32d1da6ac5532f57a828bf7332a297d7e4294055340cb3d99d97c45",
        "axis_counts": [6, 4, 8],
        "axis_sha256": {
            "x": "bb1d6be1e2cec153c7bd67a71e29f5967b3035b4928cd06f51ee2c0b6f2a5361",
            "y": "c0a1052034574ddda40b805390f8debb6abd3da6ec558cc0458820ee941198ba",
            "z": "82d51947444eb3e27d0678b92be099c1f86e7e42f5c5bfa5cefdb8ce4ea07d37",
        },
    },
    "D15-Z2-reused-H15-B": {
        "run_id": "task40_phi90_13p5_H15_B_p6_direct_v1",
        "source_sha": "d9edbcd583bb74dde36e3c9552893560f47bd230",
        "input_sha256": "ec5053a0d24e0e737faaccba027864e59cf0508aa63324f2bb2afc463cc18ec4",
        "physical_model_sha256": "515971779c8348f4914dad6a098bbc2c1f1dc4d22639779a71c3697cd7fe5974",
        "resolved_config_sha256": "ae4f6fde9a0ec10db248f75f23c53dca69ce4760022aaacbdbfac3629e38d104",
        "axis_counts": [6, 4, 10],
        "axis_sha256": {
            "x": "bb1d6be1e2cec153c7bd67a71e29f5967b3035b4928cd06f51ee2c0b6f2a5361",
            "y": "c0a1052034574ddda40b805390f8debb6abd3da6ec558cc0458820ee941198ba",
            "z": "bb32b94989a71ad930f909244cfada93e60634920ffdbf156378ae8f5df6888d",
        },
    },
}
MODE_SHA = "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
THRESHOLDS = {
    "global_R_T_A_balance_A_volume_abs": 1e-5,
    "every_active_or_power_carrying_channel_R_T_abs": 1e-6,
    "boundary_complex_amplitude_relative_l2_no_phase_fit": 1e-4,
    "same_coordinate_complex_E_H_relative_l2_no_phase_fit": 1e-4,
}
PAIRS = (("D15-B", "D15-Z1"), ("D15-B", "D15-Z2-reused-H15-B"), ("D15-Z1", "D15-Z2-reused-H15-B"))


def _load_helper() -> Any:
    helper_path = Path(__file__).with_name("compare_h15_bxyz_final.py")
    spec = importlib.util.spec_from_file_location("task40_saved_compare_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load existing saved-output comparison helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RESULTS = RESULTS
    module.RUNS = RUNS
    return module


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _axis_sha(values: list[float]) -> str:
    array = np.ascontiguousarray(np.asarray(values, dtype="<f8"))
    return hashlib.sha256(array.tobytes()).hexdigest()


def _key(row: dict[str, Any]) -> tuple[str, int, int, str]:
    return str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"])


def _key_json(key: tuple[str, int, int, str]) -> dict[str, Any]:
    return {"side": key[0], "m": key[1], "n": key[2], "polarization": key[3]}


def _complex(value: list[float]) -> complex:
    return complex(float(value[0]), float(value[1]))


def _finite_float(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite saved output scalar: {value!r}")
    return result


def _norm_pair(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    ref = np.asarray(reference)
    got = np.asarray(candidate)
    if ref.shape != got.shape or not np.isfinite(ref).all() or not np.isfinite(got).all():
        raise ValueError(f"invalid saved-array pair: {ref.shape} vs {got.shape}")
    difference = got - ref
    ref_norm = float(np.linalg.norm(ref.ravel()))
    delta_norm = float(np.linalg.norm(difference.ravel()))
    return {
        "reference_l2": ref_norm,
        "difference_l2": delta_norm,
        "relative_l2_to_reference": delta_norm / ref_norm if ref_norm else None,
        "max_abs_difference": float(np.max(np.abs(difference))) if difference.size else 0.0,
    }


def _replace_ref_key(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            ("relative_l2_to_reference" if key == "relative_l2_to_B" else key): _replace_ref_key(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_ref_key(item) for item in value]
    return value


def _case_identity(label: str, case: dict[str, Any]) -> dict[str, Any]:
    run = case["run"]
    manifest = case["manifest"]
    resolved_path = run / "resolved_config.json"
    resolved_bytes = resolved_path.read_bytes()
    resolved = json.loads(resolved_bytes)
    expected = EXPECTED[label]
    actual = {
        "run_id": manifest.get("run_id"),
        "source_sha": manifest.get("source_sha"),
        "input_sha256": manifest.get("input_sha256"),
        "physical_model_sha256": manifest.get("physical_model_sha256"),
        "resolved_config_sha256": manifest.get("resolved_config_sha256"),
    }
    for field, expected_value in expected.items():
        if field in actual and actual[field] != expected_value:
            raise ValueError(f"{label}: {field} differs from the reviewed identity")
    file_identities = {
        "input_sha256_recomputed": _sha_file(run / "input_original.dat"),
        "physical_sha256_recorded_file": (run / "physical_model_sha256.txt").read_text().strip(),
        "resolved_config_sha256_recomputed": hashlib.sha256(resolved_bytes).hexdigest(),
        "source_sha_recorded_file": (run / "source_sha.txt").read_text().strip(),
    }
    if file_identities["input_sha256_recomputed"] != actual["input_sha256"]:
        raise ValueError(f"{label}: input hash does not match manifest")
    if file_identities["physical_sha256_recorded_file"] != actual["physical_model_sha256"]:
        raise ValueError(f"{label}: physical hash file does not match manifest")
    if file_identities["resolved_config_sha256_recomputed"] != actual["resolved_config_sha256"]:
        raise ValueError(f"{label}: resolved config hash does not match manifest")
    if file_identities["source_sha_recorded_file"] != actual["source_sha"]:
        raise ValueError(f"{label}: source hash file does not match manifest")

    discretization = resolved["discretization"]
    axes = {
        axis: [float(item) for item in discretization[f"mesh_axis_{axis}_values"]]
        for axis in ("x", "y", "z")
    }
    axis_hashes = {axis: _axis_sha(values) for axis, values in axes.items()}
    if [len(axes[a]) - 1 for a in ("x", "y", "z")] != expected["axis_counts"]:
        raise ValueError(f"{label}: resolved axis cell counts differ from reviewed identity")
    if axis_hashes != expected["axis_sha256"]:
        raise ValueError(f"{label}: resolved axis hashes differ from reviewed identity")
    if case["mesh_qa"].get("axis_sha256_le_f64") != axis_hashes:
        raise ValueError(f"{label}: live mesh QA axis hashes do not match resolved axes")
    if case["mesh_qa"].get("axis_cell_counts") != expected["axis_counts"]:
        raise ValueError(f"{label}: live mesh QA counts do not match resolved axes")

    facts = case["surface_contract"]
    volume_records = facts.get("volume_quadrature_records")
    if (
        facts.get("degree") != 6
        or facts.get("active_mode_count") != 612
        or facts.get("active_mode_sha256") != MODE_SHA
        or facts.get("parent_quadrature_degree") != 28
        or facts.get("dtn_sparse_cutoff_policy") != "scale_homogeneous_relative_only_v1"
        or facts.get("dtn_sparse_cutoff_relative_tolerance") != 1e-13
        or not volume_records
        or any(row.get("quadrature_degree") != 15 or row.get("quadrature_rule") != "default" for row in volume_records)
    ):
        raise ValueError(f"{label}: mode/quadrature/cutoff identity mismatch")
    if case["power"].get("active_mode_sha256") != MODE_SHA or case["power"].get("active_mode_count") != 612:
        raise ValueError(f"{label}: saved power output mode identity mismatch")

    return {
        "display_role": (
            "D15-Z2 reused from this historical completed H15-B run; no D15-Z2 run was launched"
            if label == "D15-Z2-reused-H15-B"
            else label
        ),
        "actual_profile_run_id": actual["run_id"],
        "native_capacity_profile_identity": manifest.get("native_capacity_profile_identity"),
        "run_directory": str(run.relative_to(ROOT)),
        **actual,
        "file_hashes_recomputed_or_read": file_identities,
        "execution_mode": manifest.get("execution_mode"),
        "operator_scope": facts.get("operator_scope"),
        "terminal": {
            "workflow_phase": case["phase"].get("phase"),
            "passed": case["phase"].get("facts", {}).get("passed"),
            "run_status": case["summary"].get("status"),
            "exit_status": case["summary"].get("exit_status"),
            "descendants_cleared": case["authority"].get("descendants_cleared"),
        },
        "actual_mesh_qa": case["mesh_qa"],
        "resolved_axes_nm": axes,
        "axis_cell_counts": expected["axis_counts"],
        "axis_sha256_le_f64": axis_hashes,
        "mode_count": 612,
        "mode_sha256": MODE_SHA,
        "surface_quadrature_degree": facts.get("parent_quadrature_degree"),
        "volume_quadrature_records": volume_records,
        "dtn_sparse_cutoff_policy": facts.get("dtn_sparse_cutoff_policy"),
        "dtn_sparse_cutoff_relative_tolerance": facts.get("dtn_sparse_cutoff_relative_tolerance"),
        "full_dtn_status": facts.get("full_dtn_status"),
        "runtime": {
            "elapsed_seconds": case["authority"].get("elapsed_seconds"),
            "tree_rss_peak_bytes": case["authority"].get("sampled_process_tree_rss_peak_bytes"),
            "tree_swap_peak_bytes": case["authority"].get("sampled_process_tree_swap_peak_bytes"),
            "task_swap_activity": case["authority"].get("job_swap_activity"),
            "pss_status": case["authority"].get("pss_status"),
            "rss_hard_limit_bytes": case["authority"].get("rss_hard_limit_bytes"),
            "host_available_floor_bytes": case["authority"].get("minimum_available_bytes"),
        },
        "global_values": {
            "R_total": case["power"].get("R_total"),
            "T_total": case["power"].get("T_total"),
            "A_balance": case["power"].get("A_balance"),
            "A_volume_total": case["volume"].get("A_volume_total"),
            "energy_closure_error_port_volume": case["volume"].get("energy_closure_error_port_volume"),
        },
        "solve_residuals": {
            "condensed_relative": case["residual"].get("condensed_direct_relative"),
            "condensed_gate": case["residual"].get("condensed_direct_residual_gate"),
            "original_A6_relative": case["residual"].get("original_A6_active_rectangle_relative"),
            "original_A6_gate": case["residual"].get("original_A6_active_rectangle_relative_gate"),
            "same_factor_correction_count": case["residual"].get("same_factor_correction_count"),
            "max_same_factor_corrections": case["residual"].get("max_same_factor_corrections"),
        },
        "saved_samples": {
            "metadata": case["sample_meta"],
            "archive_path": str((case["output"] / "full3d_reference_samples.npz").relative_to(ROOT)),
        },
        "raw_resolved_sections": {key: resolved[key] for key in ("geometry", "materials", "incidence", "boundary")},
        "actual_solver_contract": {
            "p6_direct": facts.get("degree") == 6 and manifest.get("execution_mode") == "full_solve",
            "same_operator_policy": {
                "mode_sha256": MODE_SHA,
                "surface_q": facts.get("parent_quadrature_degree"),
                "volume_quadrature_records": volume_records,
                "dtn_sparse_cutoff_policy": facts.get("dtn_sparse_cutoff_policy"),
                "dtn_sparse_cutoff_relative_tolerance": facts.get("dtn_sparse_cutoff_relative_tolerance"),
            },
        },
        "_resolved_sections": {key: resolved[key] for key in ("geometry", "materials", "incidence", "boundary")},
        "_axes": axes,
    }


def _metric_delta(reference: float, candidate: float) -> dict[str, Any]:
    delta = float(candidate) - float(reference)
    return {"reference": float(reference), "candidate": float(candidate), "delta_candidate_minus_reference": delta, "absolute_delta": abs(delta)}


def _channel_group(
    reference: dict[tuple[str, int, int, str], dict[str, Any]],
    candidate: dict[tuple[str, int, int, str], dict[str, Any]],
    keys: list[tuple[str, int, int, str]],
) -> dict[str, Any]:
    result: dict[str, Any] = {"mode_count": len(keys)}
    for field in ("R", "T"):
        deltas = [(float(candidate[key][field]) - float(reference[key][field]), key) for key in keys]
        if deltas:
            delta, key = max(deltas, key=lambda pair: abs(pair[0]))
            result[field] = {
                "max_abs_delta": abs(delta),
                "signed_delta_candidate_minus_reference": delta,
                "key": _key_json(key),
                "threshold": THRESHOLDS["every_active_or_power_carrying_channel_R_T_abs"],
                "pass": abs(delta) <= THRESHOLDS["every_active_or_power_carrying_channel_R_T_abs"],
                "exceeding_channel_count": sum(abs(item[0]) > THRESHOLDS["every_active_or_power_carrying_channel_R_T_abs"] for item in deltas),
            }
        else:
            result[field] = {"max_abs_delta": 0.0, "key": None, "pass": True, "exceeding_channel_count": 0}
    return result


def _relative_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        **record,
        "relative_l2_to_reference": record.pop("relative_l2_to_B", None),
    }


def _compare_pair(
    helper: Any,
    reference_label: str,
    candidate_label: str,
    reference: dict[str, Any],
    candidate: dict[str, Any],
    csv_writer: csv.DictWriter,
) -> dict[str, Any]:
    ref_orders = reference["keyed_orders"]
    got_orders = candidate["keyed_orders"]
    if set(ref_orders) != set(got_orders) or len(ref_orders) != 612:
        raise ValueError(f"modal key set mismatch for {reference_label} -> {candidate_label}")
    keys = sorted(ref_orders, key=lambda key: (key[0], key[1], key[2], key[3]))
    class_fields = ("propagating", "power_carrying", "rayleigh_warning")
    class_mismatches = {
        name: sum(bool(ref_orders[k].get(name)) != bool(got_orders[k].get(name)) for k in keys)
        for name in class_fields
    }
    if any(class_mismatches.values()):
        raise ValueError(f"modal classification changed: {class_mismatches}")
    groups = {
        "all_612": keys,
        "top": [k for k in keys if k[0] == "top"],
        "bottom": [k for k in keys if k[0] == "bottom"],
        "propagating": [k for k in keys if bool(ref_orders[k]["propagating"])],
        "power_carrying": [k for k in keys if bool(ref_orders[k]["power_carrying"])],
        "power_carrying_but_not_propagating": [k for k in keys if bool(ref_orders[k]["power_carrying"]) and not bool(ref_orders[k]["propagating"])],
        "evanescent": [k for k in keys if not bool(ref_orders[k]["propagating"])],
        "non_power_carrying": [k for k in keys if not bool(ref_orders[k]["power_carrying"])],
    }
    channel_groups = {name: _channel_group(ref_orders, got_orders, members) for name, members in groups.items()}
    for key in keys:
        ref_row, got_row = ref_orders[key], got_orders[key]
        ref_boundary = _complex(ref_row["outgoing_amplitude_at_boundary"])
        got_boundary = _complex(got_row["outgoing_amplitude_at_boundary"])
        ref_raw, got_raw = _complex(ref_row["outgoing_amplitude"]), _complex(got_row["outgoing_amplitude"])
        csv_writer.writerow({
            "reference_case": reference_label,
            "candidate_case": candidate_label,
            "side": key[0], "m": key[1], "n": key[2], "polarization": key[3],
            "propagating": bool(ref_row["propagating"]),
            "power_carrying": bool(ref_row["power_carrying"]),
            "reference_R": ref_row["R"], "candidate_R": got_row["R"],
            "delta_R": float(got_row["R"]) - float(ref_row["R"]),
            "reference_T": ref_row["T"], "candidate_T": got_row["T"],
            "delta_T": float(got_row["T"]) - float(ref_row["T"]),
            "reference_boundary_re": ref_boundary.real, "reference_boundary_im": ref_boundary.imag,
            "candidate_boundary_re": got_boundary.real, "candidate_boundary_im": got_boundary.imag,
            "boundary_delta_abs": abs(got_boundary - ref_boundary),
            "boundary_delta_rel_to_reference_mode": abs(got_boundary - ref_boundary) / abs(ref_boundary) if abs(ref_boundary) else "",
            "reference_raw_outgoing_re": ref_raw.real, "reference_raw_outgoing_im": ref_raw.imag,
            "candidate_raw_outgoing_re": got_raw.real, "candidate_raw_outgoing_im": got_raw.imag,
        })

    global_names = ("R_total", "T_total", "A_balance")
    globals_result = {
        name: _metric_delta(_finite_float(reference["power"][name]), _finite_float(candidate["power"][name]))
        for name in global_names
    }
    globals_result["A_volume_total"] = _metric_delta(
        _finite_float(reference["volume"]["A_volume_total"]),
        _finite_float(candidate["volume"]["A_volume_total"]),
    )
    for record in globals_result.values():
        record["threshold"] = THRESHOLDS["global_R_T_A_balance_A_volume_abs"]
        record["pass"] = record["absolute_delta"] <= record["threshold"]
    r00_global = {
        name: _metric_delta(_finite_float(reference["power"][name]), _finite_float(candidate["power"][name]))
        for name in ("R00_s", "R00_total")
    }
    for record in r00_global.values():
        record["threshold"] = THRESHOLDS["every_active_or_power_carrying_channel_R_T_abs"]
        record["pass"] = record["absolute_delta"] <= record["threshold"]
    key_00_s = ("top", 0, 0, "s")
    key_00_total = ("top", 0, 0, "total")
    r00 = {}
    for name, key in (("R00_s", key_00_s), ("R00_total", key_00_total)):
        if key in ref_orders:
            r00[name] = {
                "key": _key_json(key),
                "R": _metric_delta(_finite_float(ref_orders[key]["R"]), _finite_float(got_orders[key]["R"])),
                "T": _metric_delta(_finite_float(ref_orders[key]["T"]), _finite_float(got_orders[key]["T"])),
            }
            for kind in ("R", "T"):
                r00[name][kind]["threshold"] = THRESHOLDS["every_active_or_power_carrying_channel_R_T_abs"]
                r00[name][kind]["pass"] = r00[name][kind]["absolute_delta"] <= r00[name][kind]["threshold"]

    boundary_all = _norm_pair(
        np.asarray([_complex(ref_orders[k]["outgoing_amplitude_at_boundary"]) for k in keys]),
        np.asarray([_complex(got_orders[k]["outgoing_amplitude_at_boundary"]) for k in keys]),
    )
    boundary_groups = {
        name: _norm_pair(
            np.asarray([_complex(ref_orders[k]["outgoing_amplitude_at_boundary"]) for k in members]),
            np.asarray([_complex(got_orders[k]["outgoing_amplitude_at_boundary"]) for k in members]),
        )
        for name, members in groups.items()
    }
    boundary_all["threshold"] = THRESHOLDS["boundary_complex_amplitude_relative_l2_no_phase_fit"]
    boundary_all["pass"] = boundary_all["relative_l2_to_reference"] is not None and boundary_all["relative_l2_to_reference"] <= boundary_all["threshold"]

    fields = _replace_ref_key(helper._compare_fields(reference, candidate))
    e_h = fields["E_H"]
    field_gate = {
        field_name: {
            "relative_l2_to_reference": e_h[field_name]["all_points_and_components"].get("relative_l2_to_reference"),
            "threshold": THRESHOLDS["same_coordinate_complex_E_H_relative_l2_no_phase_fit"],
            "pass": e_h[field_name]["all_points_and_components"].get("relative_l2_to_reference") is not None
            and e_h[field_name]["all_points_and_components"]["relative_l2_to_reference"] <= THRESHOLDS["same_coordinate_complex_E_H_relative_l2_no_phase_fit"],
        }
        for field_name in ("E_V_per_m", "H_A_per_m")
    }
    gate_pass = (
        all(item["pass"] for item in globals_result.values())
        and all(channel_groups["all_612"][name]["pass"] for name in ("R", "T"))
        and all(channel_groups["power_carrying"][name]["pass"] for name in ("R", "T"))
        and all(record["pass"] for record in r00_global.values())
        and boundary_all["pass"]
        and all(record["pass"] for record in field_gate.values())
    )
    return {
        "reference_case": reference_label,
        "candidate_case": candidate_label,
        "pair_gate": "PASS" if gate_pass else "FAIL",
        "comparison_thresholds": THRESHOLDS,
        "global_observables": globals_result,
        "R00_global_crosscheck_at_per_channel_threshold": r00_global,
        "all_active_and_power_carrying_channels": "threshold is checked over all 612; power-carrying subset is also reported independently",
        "channel_groups": channel_groups,
        "R00_s_and_R00_total": r00,
        "modal_classification_mismatch_counts": class_mismatches,
        "boundary_complex_amplitude_all_612": boundary_all,
        "boundary_complex_amplitude_by_group": boundary_groups,
        "same_coordinate_complex_E_H": field_gate,
        "saved_field_comparison": fields,
        "interpretation_limits": {
            "no_phase_fit_or_interpolation": True,
            "horizontal_Et_Ht_are_diagnostics_only": True,
            "canonical_pillar_sidewall_Et_Ht": "NOT_MEASURED",
            "full_DtN": "FULL_DTN_NOT_VERIFIED",
            "finite_R13_rectangle_only": True,
        },
    }


def main() -> None:
    helper = _load_helper()
    cases = {label: helper._read_case(label) for label in RUNS}
    identities = {label: _case_identity(label, case) for label, case in cases.items()}
    section_names = ("geometry", "materials", "incidence", "boundary")
    physical_sections_match = all(
        identities[label]["_resolved_sections"] == identities["D15-B"]["_resolved_sections"]
        for label in identities
    )
    if not physical_sections_match:
        raise ValueError("geometry/materials/incidence/boundary differ across saved cases")
    # All cases retain the base x/y axes; z is the only changed mesh axis.
    base_axes = identities["D15-B"]["_axes"]
    for label in ("D15-Z1", "D15-Z2-reused-H15-B"):
        if identities[label]["_axes"]["x"] != base_axes["x"] or identities[label]["_axes"]["y"] != base_axes["y"]:
            raise ValueError(f"{label} does not preserve D15-B x/y axes")
        if identities[label]["_axes"]["z"] == base_axes["z"]:
            raise ValueError(f"{label} does not have a distinct z mesh")
    # Ensure same physical/quadrature/modal/cutoff contract even though source/profile IDs differ.
    contract_tuples = {
        label: (
            case["power"].get("active_mode_sha256"),
            case["surface_contract"].get("parent_quadrature_degree"),
            json.dumps(case["surface_contract"].get("volume_quadrature_records"), sort_keys=True),
            case["surface_contract"].get("dtn_sparse_cutoff_policy"),
            case["surface_contract"].get("dtn_sparse_cutoff_relative_tolerance"),
        )
        for label, case in cases.items()
    }
    if len(set(contract_tuples.values())) != 1:
        raise ValueError("mode, quadrature, or sparse-cutoff operator contract differs")

    csv_path = RECORDS / "d15_b_z1_z2_all_612_modes_20261022_v1.csv"
    json_path = RECORDS / "d15_b_z1_z2_saved_output_comparison_20261022_v1.json"
    RECORDS.mkdir(parents=True, exist_ok=True)
    csv_fields = [
        "reference_case", "candidate_case", "side", "m", "n", "polarization", "propagating", "power_carrying",
        "reference_R", "candidate_R", "delta_R", "reference_T", "candidate_T", "delta_T",
        "reference_boundary_re", "reference_boundary_im", "candidate_boundary_re", "candidate_boundary_im",
        "boundary_delta_abs", "boundary_delta_rel_to_reference_mode",
        "reference_raw_outgoing_re", "reference_raw_outgoing_im", "candidate_raw_outgoing_re", "candidate_raw_outgoing_im",
    ]
    comparisons = {}
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=csv_fields, lineterminator="\n")
        writer.writeheader()
        for reference_label, candidate_label in PAIRS:
            key = f"{reference_label}_vs_{candidate_label}"
            comparisons[key] = _compare_pair(
                helper, reference_label, candidate_label,
                cases[reference_label], cases[candidate_label], writer,
            )

    for identity in identities.values():
        identity.pop("_resolved_sections")
        identity.pop("_axes")
    csv_sha256 = _sha_file(csv_path)
    payload = {
        "schema": "task40.d15_b_z1_reused_h15_b_z2_saved_output_comparison.v1",
        "analysis_script": {
            "path": str(Path(__file__).relative_to(ROOT)),
            "sha256": _sha_file(Path(__file__)),
        },
        "created_from": "offline saved outputs only; no mesh/FE/factor/solve, no VTU, no resource stream",
        "physical_sections_identical": {name: True for name in section_names},
        "mesh_lineage": {
            "D15-B_to_D15-Z1": "only z changed; x/y actual axis hashes are identical",
            "D15-B_to_D15-Z2_role": "D15-Z2 reuses the already completed historical H15-B run; only z differs from D15-B, and no new D15-Z2 run was launched",
            "D15-Z1_to_reused_D15-Z2": "same x/y axes; z resolution differs",
            "cross_mesh_FE_reuse": False,
        },
        "operator_identity": {
            "source_SHAs_are_not_identical": len({identity["source_sha"] for identity in identities.values()}) > 1,
            "all_use_p6_full_solve": True,
            "mode_count": 612,
            "mode_sha256": MODE_SHA,
            "surface_quadrature_degree": 28,
            "volume_quadrature": {"degree": 15, "rule": "default"},
            "dtn_sparse_cutoff_policy": "scale_homogeneous_relative_only_v1",
            "dtn_sparse_cutoff_relative_tolerance": 1e-13,
            "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
            "geometry_materials_incidence_boundary": "identical in the saved resolved configs",
        },
        "thresholds": THRESHOLDS,
        "cases": identities,
        "comparisons": comparisons,
        "limitations": [
            "H15-B is reused as the D15-Z2 comparison role without renaming or rewriting its historical run/source/manifest.",
            "The source/profile identities differ across runs; common physics, active R13 modes, quadrature, and cutoff contracts were checked explicitly.",
            "The three-group comparison covers saved R/T/A, all 612 per-channel powers, boundary modal amplitudes, and same-coordinate sampled complex E/H under the stated thresholds.",
            "Saved horizontal Et/Ht remain diagnostics and do not measure canonical pillar sidewalls.",
            "Finite R13 outputs do not establish full DtN convergence or authority beyond the recorded mode rectangle.",
        ],
        "output_files": {"all_612_mode_csv": {"path": str(csv_path.relative_to(ROOT)), "sha256": csv_sha256, "rows": 3 * 612}},
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "json": str(json_path.relative_to(ROOT)),
        "json_sha256": _sha_file(json_path),
        "csv": str(csv_path.relative_to(ROOT)),
        "csv_sha256": _sha_file(csv_path),
        "pair_gates": {key: value["pair_gate"] for key, value in comparisons.items()},
        "csv_rows": sum(1 for _ in csv_path.open(encoding="utf-8")) - 1,
        "run_npz_loads": len(cases),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
