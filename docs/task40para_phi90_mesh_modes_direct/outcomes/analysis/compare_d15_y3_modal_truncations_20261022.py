"""Compare four D15-Y3 modal rectangles against its saved finite R13 parent."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[4]
RESULTS = REPO / "results/si_block_phi90_50x50_17x20_h120"
RECORDS = REPO / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
JSON_PATH = RECORDS / "d15_y3_modal_truncation_comparison_20261022_v1.json"
CSV_PATH = RECORDS / "d15_y3_modal_truncation_all_612_20261022_v1.csv"
HELPER_PATH = Path(__file__).resolve().parent / "compare_d13_same_policy_y2_y3.py"
PARENT_MODE_SHA = "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
PHYSICAL_SHA = "ce77eb0b9e32affdcd51da2159e5d05caf28807a32def69618546350b1bfe861"
AXIS_SHA = {
    "x": "bb1d6be1e2cec153c7bd67a71e29f5967b3035b4928cd06f51ee2c0b6f2a5361",
    "y": "3c5e071970351e7b894027da1880869ff7a784370a752a10db2febfd88020d25",
    "z": "daf722948a31d19757622ba67544eeea6d49fdc2e433b979df9c11b2b450afb6",
}
THRESHOLDS = {
    "global_R_T_A_balance_A_volume_absolute": 1.0e-5,
    "per_channel_R_T_absolute_all_parent_modes": 1.0e-6,
    "boundary_complex_amplitude_relative_l2_no_phase_fit": 1.0e-4,
    "same_coordinate_complex_E_H_relative_l2_no_phase_fit": 1.0e-4,
}
SAMPLE_FIELDS = (
    "E_V_per_m",
    "H_A_per_m",
    "E_t_interface_V_per_m",
    "H_t_interface_A_per_m",
)
IDENTITY_FIELDS = (
    "medium",
    "beta",
    "boundary_phase",
    "propagating",
    "power_carrying",
    "refractive_index",
    "kz",
    "alpha",
    "gamma",
    "vertical_sign",
)
CASES = {
    "Y3_R13_612": {
        "directory": "task40_phi90_13p5_D15_Y3_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261021T081011.745578Z",
        "display": "D15-Y3 finite R13 parent",
        "K": None,
        "source_sha": "ba26075e2a871db10a81efbceeb32b51d95ea96b",
        "input_sha256": "bf27bd09cb2b01509b13d2da414919db8b14fd49842e632cfa932fb00baa5943",
        "resolved_config_sha256": "05b05b5518fd889fab9788e3a740f92f01b9fab0a7ae132172c620d8ea8079e4",
        "mode_count": 612,
        "mode_sha256": PARENT_MODE_SHA,
    },
    "K1": {
        "directory": "task40_phi90_13p5_D15_Y3_K1_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261022T155649.539690Z",
        "display": "D15-Y3-K1, m,n in [-1,1]",
        "K": 1,
        "source_sha": "b4df11e06fd02be27b33df1f432123203ac5009f",
        "input_sha256": "07d80e25f6607122e743e3ea9408962d3b3d0fe3d10fa0733794fcf081cfb155",
        "resolved_config_sha256": "c4b821852be86f503802798e968c20e2bb02f7abad03aaea11666a25736ab15c",
        "mode_count": 36,
        "mode_sha256": "045b996778c449bf8be5bfcf155d2a1f752b1a5b4ae2dfae2ba98ec51c24e7b2",
        "selected_parent_indices_sha256": "d403f108e833abba7454e101324ecb14fbef8afa4b45eb8dc613f876da409019",
        "selected_signed_keys_sha256": "e7a48c62f8fceec071f1bc3b0d43708f7fc87273237f6acf546b1fbd64ee4a12",
    },
    "K2": {
        "directory": "task40_phi90_13p5_D15_Y3_K2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261022T164206.047284Z",
        "display": "D15-Y3-K2, m,n in [-2,2]",
        "K": 2,
        "source_sha": "b4df11e06fd02be27b33df1f432123203ac5009f",
        "input_sha256": "09868122be1985943f7f2a980651a645ee2e0471d22435ad54cc4586854e8b5b",
        "resolved_config_sha256": "214489b8d7cd0e60572ea5cb31e6757cb7c9272049577a4c502959f7ba0cafb0",
        "mode_count": 100,
        "mode_sha256": "b6511864775f7a3280c8690babccd23c106930e00e027d441082568cdc2f597d",
        "selected_parent_indices_sha256": "a92236ece070466c4fe76c63aa40c410dd698a72c9bccebe241c4efd3f3bc6de",
        "selected_signed_keys_sha256": "c221867bc88c744bcfdef54ec95453112a7064832914c095e351bf89f48e9d2b",
    },
    "K3": {
        "directory": "task40_phi90_13p5_D15_Y3_K3_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261022T171203.124116Z",
        "display": "D15-Y3-K3, m,n in [-3,3]",
        "K": 3,
        "source_sha": "b4df11e06fd02be27b33df1f432123203ac5009f",
        "input_sha256": "6b394436f196afc50210c6e3a7830619a24f25ee1f4a51c1d04e1977a5c90767",
        "resolved_config_sha256": "22a416c6e090f20511cf9cf854ffd83ae2fed4e82cb613517a6196a8bff1cb5c",
        "mode_count": 196,
        "mode_sha256": "398b7db8c26e7b30ff198410b45ac2415ec8a785670fe351d3990781f056ae98",
        "selected_parent_indices_sha256": "dce336c56a7a3e9ce2c092fba29e602b625ba693b55bca5e57a682ed1cce9e20",
        "selected_signed_keys_sha256": "15d52238a648bcd8908ed3f8799f0dc991b472c1de8add1132ec416600a3b147",
    },
    "K4": {
        "directory": "task40_phi90_13p5_D15_Y3_K4_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261022T174008.821628Z",
        "display": "D15-Y3-K4, m,n in [-4,4]",
        "K": 4,
        "source_sha": "b4df11e06fd02be27b33df1f432123203ac5009f",
        "input_sha256": "914efd738662e72073b013952417e1585724a568eb0deb83ab060d3b4641226b",
        "resolved_config_sha256": "15e8815b9c2568ffb078c083b1ba0d373f371ded2de8b4e0ac365a386ec66f33",
        "mode_count": 324,
        "mode_sha256": "c7281da5bfadbc9716e7cbcbe952037b592b59432e264db1632cf344af9edf89",
        "selected_parent_indices_sha256": "02abef46a37c04318dd997cce1df177b672c68b0a8ae6c385e4805ca22c5e6bd",
        "selected_signed_keys_sha256": "8bf6295a5c3249fddef80b52d4588a1b8cd778d34a5fabef8a1e949c100af616",
    },
}
CORE_NUMERICAL_FILES = (
    "src/solvers/p6_condensed_direct.py",
    "src/solvers/p6_cell_condensed_action.py",
    "src/solvers/fullspace_dtn_action.py",
    "src/solvers/dtn_port_3d.py",
    "src/runners/physical_retained_condensed_v20.py",
)


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> tuple[Any, str]:
    raw = path.read_bytes()
    return json.loads(raw), sha_bytes(raw)


def json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def helper_module() -> Any:
    spec = importlib.util.spec_from_file_location("task40_modal_truncation_helpers", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import comparison helpers from {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_path(spec: dict[str, Any]) -> Path:
    return RESULTS / spec["directory"] / spec["stamp"]


def load_case(label: str, spec: dict[str, Any], helper: Any) -> dict[str, Any]:
    run = run_path(spec)
    output = run / "numerical_output"
    summary, summary_sha = read_json(run / "run_summary.json")
    manifest, manifest_sha = read_json(run / "run_manifest.json")
    phase, phase_sha = read_json(run / "workflow_phase.json")
    direct, direct_sha = read_json(run / "p6_condensed_direct_summary.json")
    power, power_sha = read_json(output / "dtn_port_power_metrics_3d.json")
    volume, volume_sha = read_json(output / "volume_absorption.json")
    diffraction, diffraction_sha = read_json(output / "dtn_port_diffraction_orders_3d.json")
    auxiliary, auxiliary_sha = read_json(output / "dtn_auxiliary_amplitudes_3d.json")
    sample_meta, sample_meta_sha = read_json(output / "full3d_reference_samples.json")

    for field in ("source_sha", "input_sha256", "resolved_config_sha256"):
        expected = spec.get(field)
        if expected is not None and manifest.get(field) != expected:
            raise ValueError(f"{label}: {field} mismatch: {manifest.get(field)} != {expected}")
    if manifest.get("physical_model_sha256") != PHYSICAL_SHA:
        raise ValueError(f"{label}: physical model identity mismatch")
    if summary.get("status") != "finished" or summary.get("exit_status") != 0:
        raise ValueError(f"{label}: run did not finish with exit 0")
    resource = summary["resource_authority"]
    if not resource["descendants_cleared"] or resource["remaining_child_pids"]:
        raise ValueError(f"{label}: descendant cleanup is incomplete")
    if direct.get("passed") is not True or direct.get("complete_solve") is not True:
        raise ValueError(f"{label}: direct full solve gate failed")
    if phase.get("facts", {}).get("passed") is not True:
        raise ValueError(f"{label}: workflow completion facts do not pass")
    if power.get("full_dtn_status") != "FULL_DTN_NOT_VERIFIED":
        raise ValueError(f"{label}: finite-R13 limitation marker changed")
    if power.get("output_scope") != "ACTIVE_FE_DTN_PORTS":
        raise ValueError(f"{label}: unexpected port output scope")
    if power.get("active_mode_count") != spec["mode_count"] or power.get("active_mode_sha256") != spec["mode_sha256"]:
        raise ValueError(f"{label}: active mode identity/count mismatch")
    if power.get("parent_mode_count") != 612 or power.get("parent_mode_sha256") != PARENT_MODE_SHA:
        raise ValueError(f"{label}: finite R13 parent identity mismatch")
    rows = diffraction.get("orders", [])
    if len(rows) != spec["mode_count"] or len(auxiliary) != spec["mode_count"]:
        raise ValueError(f"{label}: diffraction/auxiliary row count mismatch")
    keys = [helper._key(row) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{label}: duplicate signed modal keys")
    if any(helper._key(row) != helper._key(auxiliary[i]) for i, row in enumerate(rows)):
        raise ValueError(f"{label}: diffraction/auxiliary signed key ordering differs")

    mesh = direct.get("mesh_evidence", {})
    if mesh.get("axis_cell_counts") != [6, 10, 6] or mesh.get("actual_global_cell_count") != 360:
        raise ValueError(f"{label}: actual mesh counts do not match D15-Y3")
    if mesh.get("axis_sha256_le_f64") != AXIS_SHA:
        raise ValueError(f"{label}: axis hashes differ from the original Y3 grid")
    operator = direct["operator_identity"]
    if operator.get("degree") != 6 or operator.get("parent_quadrature_degree") != 28:
        raise ValueError(f"{label}: p6/surface-q28 contract mismatch")
    if direct["production_port_mpc_witness"].get("dtn_quadrature_degree") != 28:
        raise ValueError(f"{label}: production port witness is not q28")
    if operator.get("dtn_sparse_cutoff_policy") != "scale_homogeneous_relative_only_v1":
        raise ValueError(f"{label}: sparse-cutoff policy mismatch")
    if operator.get("dtn_sparse_cutoff_relative_tolerance") != 1e-13:
        raise ValueError(f"{label}: sparse-cutoff tolerance mismatch")
    volume_records = operator.get("volume_quadrature_records")
    if not volume_records or any(r.get("quadrature_degree") != 15 or r.get("quadrature_rule") != "default" for r in volume_records):
        raise ValueError(f"{label}: q15/default volume integration mismatch")
    if direct["residuals"]["condensed_direct_relative"] > direct["residuals"]["condensed_direct_residual_gate"]:
        raise ValueError(f"{label}: condensed residual gate failed")
    if direct["residuals"]["original_A6_active_rectangle_relative"] > direct["residuals"]["original_A6_active_rectangle_relative_gate"]:
        raise ValueError(f"{label}: active-rectangle A6 gate failed")
    if direct["factor"]["same_factor_correction_count"] > 2:
        raise ValueError(f"{label}: same-factor correction limit exceeded")

    npz_path = output / "full3d_reference_samples.npz"
    sample_raw = npz_path.read_bytes()
    if len(sample_raw) != sample_meta.get("archive_bytes") or sha_bytes(sample_raw) != sample_meta.get("archive_sha256"):
        raise ValueError(f"{label}: small sample archive hash/size mismatch")
    with np.load(io.BytesIO(sample_raw), allow_pickle=False) as archive:
        samples = {name: archive[name].copy() for name in archive.files}
    required = (*SAMPLE_FIELDS, "x_nm", "y_nm", "z_nm")
    if any(name not in samples for name in required):
        raise ValueError(f"{label}: required same-coordinate sample field missing")

    solver = direct["residuals"]
    axis_tags = mesh.get("material_tag_counts")
    return {
        "label": label,
        "display": spec["display"],
        "K": spec["K"],
        "run": str(run),
        "source_sha": manifest["source_sha"],
        "input_sha256": manifest["input_sha256"],
        "physical_model_sha256": manifest["physical_model_sha256"],
        "resolved_config_sha256": manifest["resolved_config_sha256"],
        "run_manifest_sha256": manifest_sha,
        "run_summary_sha256": summary_sha,
        "workflow_phase_sha256": phase_sha,
        "direct_summary_sha256": direct_sha,
        "classification": summary["result_classification"],
        "exit_status": summary["exit_status"],
        "elapsed_seconds": resource["elapsed_seconds"],
        "tree_rss_peak_bytes": resource["sampled_process_tree_rss_peak_bytes"],
        "tree_swap_peak_bytes": resource["sampled_process_tree_swap_peak_bytes"],
        "pss_status": resource["pss_status"],
        "mesh": {
            "axis_cell_counts": mesh["axis_cell_counts"],
            "actual_global_cell_count": mesh["actual_global_cell_count"],
            "axis_sha256_le_f64": mesh["axis_sha256_le_f64"],
            "material_tag_counts": axis_tags,
        },
        "modes": {
            "active_count": power["active_mode_count"],
            "active_sha256": power["active_mode_sha256"],
            "parent_count": power["parent_mode_count"],
            "parent_sha256": power["parent_mode_sha256"],
            "selected_parent_indices_sha256": power["selected_parent_indices_sha256"],
            "selected_signed_keys_sha256": (operator.get("operator_selection") or {}).get("selected_signed_keys_sha256"),
            "rectangle_max_abs_m_n": (operator.get("operator_selection") or {}).get("active_rectangle_max_abs_m_n"),
            "propagating_count": power["dtn_port_propagating_mode_count"],
        },
        "quadrature": {
            "surface_degree": direct["production_port_mpc_witness"]["dtn_quadrature_degree"],
            "volume_records": volume_records,
        },
        "cutoff": {
            "policy": operator["dtn_sparse_cutoff_policy"],
            "relative_tolerance": operator["dtn_sparse_cutoff_relative_tolerance"],
            "identity_sha256": operator["dtn_sparse_cutoff_identity_sha256"],
        },
        "solver": {
            "condensed_relative": solver["condensed_direct_relative"],
            "condensed_limit": solver["condensed_direct_residual_gate"],
            "active_A6_relative": solver["original_A6_active_rectangle_relative"],
            "active_A6_limit": solver["original_A6_active_rectangle_relative_gate"],
            "same_factor_corrections": direct["factor"]["same_factor_correction_count"],
            "energy_closure_abs": abs(volume["energy_closure_error_port_volume"]),
        },
        "totals": {
            "R_total": power["R_total"],
            "T_total": power["T_total"],
            "A_balance": power["A_balance"],
            "A_volume": volume["A_volume_total"],
            "R00_s": power["R00_s"],
            "R00_p": power["R00_p"],
            "R00_total": power["R00_s"] + power["R00_p"],
            "energy_closure_signed": volume["energy_closure_error_port_volume"],
            "A_grating": volume["A_grating"],
            "A_substrate": volume["A_substrate"],
        },
        "full_dtn_status": power["full_dtn_status"],
        "modal_orders": rows,
        "auxiliary_rows": auxiliary,
        "samples": samples,
        "sample_metadata": sample_meta,
        "sample_npz_sha256": sample_meta["archive_sha256"],
        "artifact_hashes": {
            "power_metrics_sha256": power_sha,
            "volume_absorption_sha256": volume_sha,
            "diffraction_orders_sha256": diffraction_sha,
            "auxiliary_sha256": auxiliary_sha,
            "sample_metadata_sha256": sample_meta_sha,
        },
    }


def complex_value(pair: list[float]) -> complex:
    return complex(float(pair[0]), float(pair[1]))


def finite_rows(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    for row in rows:
        for field in fields:
            if not math.isfinite(float(row[field])):
                raise ValueError(f"nonfinite {field} at {helper_module()._key(row)}")


def max_delta(values: np.ndarray, keys: list[tuple[str, str, int, int, str]]) -> dict[str, Any]:
    if values.size == 0:
        return {"max_abs_delta": 0.0, "signed_delta_at_max": 0.0, "key": None, "violations_over_1e-6": 0}
    i = int(np.argmax(np.abs(values)))
    return {
        "max_abs_delta": float(abs(values[i])),
        "signed_delta_at_max": float(values[i]),
        "key": list(keys[i]),
        "violations_over_1e-6": int(np.count_nonzero(np.abs(values) > THRESHOLDS["per_channel_R_T_absolute_all_parent_modes"])),
    }


def compare_one(reference: dict[str, Any], candidate: dict[str, Any], helper: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    parent_rows = reference["modal_orders"]
    candidate_rows = candidate["modal_orders"]
    parent_keys = [helper._key(row) for row in parent_rows]
    parent_by_key = {helper._key(row): row for row in parent_rows}
    candidate_by_key = {helper._key(row): row for row in candidate_rows}
    if len(parent_keys) != 612 or len(parent_by_key) != 612:
        raise ValueError("reference must contain exactly 612 unique signed mode keys")
    if not set(candidate_by_key).issubset(parent_by_key):
        raise ValueError(f"{candidate['label']}: candidate includes keys outside the parent R13 set")
    expected_count = 4 * (2 * int(candidate["K"]) + 1) ** 2
    if len(candidate_by_key) != expected_count or len(candidate_by_key) != candidate["modes"]["active_count"]:
        raise ValueError(f"{candidate['label']}: actual mode count does not match rectangle formula")
    for key, crow in candidate_by_key.items():
        if abs(key[2]) > candidate["K"] or abs(key[3]) > candidate["K"]:
            raise ValueError(f"{candidate['label']}: mode outside the requested symmetric m,n rectangle: {key}")
        prow = parent_by_key[key]
        for field in IDENTITY_FIELDS:
            if crow[field] != prow[field]:
                raise ValueError(f"{candidate['label']}: parent modal identity differs for {key} field {field}")
    finite_rows(parent_rows, ("R", "T"))
    finite_rows(candidate_rows, ("R", "T"))

    candidate_presence = np.asarray([key in candidate_by_key for key in parent_keys], dtype=bool)
    parent_r = np.asarray([float(row["R"]) for row in parent_rows], dtype=np.float64)
    parent_t = np.asarray([float(row["T"]) for row in parent_rows], dtype=np.float64)
    candidate_r = np.asarray([float(candidate_by_key[key]["R"]) if key in candidate_by_key else 0.0 for key in parent_keys], dtype=np.float64)
    candidate_t = np.asarray([float(candidate_by_key[key]["T"]) if key in candidate_by_key else 0.0 for key in parent_keys], dtype=np.float64)
    delta_r = candidate_r - parent_r
    delta_t = candidate_t - parent_t
    class_masks = {
        "all_612_parent_keys": np.ones(612, dtype=bool),
        "propagating": np.asarray([bool(row["propagating"]) for row in parent_rows]),
        "power_carrying": np.asarray([bool(row["power_carrying"]) for row in parent_rows]),
        "power_carrying_but_not_propagating": np.asarray([bool(row["power_carrying"]) and not bool(row["propagating"]) for row in parent_rows]),
        "evanescent_nonpropagating": np.asarray([not bool(row["propagating"]) for row in parent_rows]),
        "non_power_carrying": np.asarray([not bool(row["power_carrying"]) for row in parent_rows]),
        "omitted_parent_tail": ~candidate_presence,
    }
    mode_groups: dict[str, Any] = {}
    for group, mask in class_masks.items():
        indices = np.flatnonzero(mask)
        keys = [parent_keys[int(i)] for i in indices]
        dr = delta_r[indices]
        dt = delta_t[indices]
        mode_groups[group] = {
            "parent_count": int(indices.size),
            "candidate_present_count": int(np.count_nonzero(candidate_presence[indices])),
            "omitted_count": int(indices.size - np.count_nonzero(candidate_presence[indices])),
            "R": max_delta(dr, keys),
            "T": max_delta(dt, keys),
            "delta_l2_R": float(np.linalg.norm(dr)),
            "delta_l2_T": float(np.linalg.norm(dt)),
            "omitted_parent_sum_R": float(np.sum(parent_r[indices[~candidate_presence[indices]]])),
            "omitted_parent_sum_T": float(np.sum(parent_t[indices[~candidate_presence[indices]]])),
            "omitted_parent_sum_modal_power_code_units": float(sum(float(parent_rows[int(i)]["modal_power_code_units"]) for i in indices if not candidate_presence[int(i)])),
        }

    omitted_indices = np.flatnonzero(~candidate_presence)
    omitted_boundary = np.asarray([complex_value(parent_rows[int(i)]["outgoing_amplitude_at_boundary"]) for i in omitted_indices], dtype=np.complex128)
    parent_boundary = np.asarray([complex_value(row["outgoing_amplitude_at_boundary"]) for row in parent_rows], dtype=np.complex128)
    candidate_boundary = np.asarray([
        complex_value(candidate_by_key[key]["outgoing_amplitude_at_boundary"]) if key in candidate_by_key else 0.0j
        for key in parent_keys
    ], dtype=np.complex128)
    boundary_metrics = helper._norm_metrics(parent_boundary, candidate_boundary)
    boundary_delta = candidate_boundary - parent_boundary
    boundary_max_index = int(np.argmax(np.abs(boundary_delta)))
    boundary_top = [
        {"key": list(parent_keys[int(i)]), "abs_delta": float(abs(boundary_delta[int(i)]))}
        for i in np.argsort(np.abs(boundary_delta))[::-1][:10]
    ]
    tail_boundary_l2 = float(np.linalg.norm(omitted_boundary))
    tail_boundary_max = float(np.max(np.abs(omitted_boundary), initial=0.0))

    global_fields = ("R_total", "T_total", "A_balance", "A_volume")
    global_metrics = {}
    for field in global_fields:
        ref_value = float(reference["totals"][field])
        cand_value = float(candidate["totals"][field])
        difference = cand_value - ref_value
        global_metrics[field] = {
            "reference": ref_value,
            "candidate": cand_value,
            "signed_delta_candidate_minus_reference": difference,
            "absolute_delta": abs(difference),
            "limit": THRESHOLDS["global_R_T_A_balance_A_volume_absolute"],
            "pass": abs(difference) <= THRESHOLDS["global_R_T_A_balance_A_volume_absolute"],
        }
    all_modes = mode_groups["all_612_parent_keys"]
    power_carrying = mode_groups["power_carrying"]
    channel_gate = {
        "all_612_parent_keys_R_pass": all_modes["R"]["max_abs_delta"] <= THRESHOLDS["per_channel_R_T_absolute_all_parent_modes"],
        "all_612_parent_keys_T_pass": all_modes["T"]["max_abs_delta"] <= THRESHOLDS["per_channel_R_T_absolute_all_parent_modes"],
        "power_carrying_R_pass": power_carrying["R"]["max_abs_delta"] <= THRESHOLDS["per_channel_R_T_absolute_all_parent_modes"],
        "power_carrying_T_pass": power_carrying["T"]["max_abs_delta"] <= THRESHOLDS["per_channel_R_T_absolute_all_parent_modes"],
    }
    boundary_gate = {
        "relative_l2_no_phase_fit": boundary_metrics["relative_l2_to_reference"],
        "delta_l2": boundary_metrics["delta_l2"],
        "reference_l2": boundary_metrics["reference_l2"],
        "candidate_zero_extended_l2": boundary_metrics["candidate_l2"],
        "max_abs_delta": float(abs(boundary_delta[boundary_max_index])),
        "max_delta_key": list(parent_keys[boundary_max_index]),
        "top_10_absolute_deltas": boundary_top,
        "threshold": THRESHOLDS["boundary_complex_amplitude_relative_l2_no_phase_fit"],
        "pass": boundary_metrics["relative_l2_to_reference"] is not None and boundary_metrics["relative_l2_to_reference"] <= THRESHOLDS["boundary_complex_amplitude_relative_l2_no_phase_fit"],
        "zero_extension_over_all_parent_612_keys": True,
    }

    sample_comparisons = {}
    coordinate_checks = {}
    for axis in ("x_nm", "y_nm", "z_nm"):
        a = reference["samples"][axis]
        b = candidate["samples"][axis]
        equal = a.shape == b.shape and np.array_equal(a, b)
        coordinate_checks[axis] = {
            "exactly_equal": bool(equal),
            "shape": list(a.shape),
            "sha256": helper._array_sha(a),
        }
        if not equal:
            raise ValueError(f"{candidate['label']}: saved sample coordinate {axis} differs; no interpolation permitted")
    for field in SAMPLE_FIELDS:
        a = reference["samples"][field]
        b = candidate["samples"][field]
        if a.shape != b.shape:
            raise ValueError(f"{candidate['label']}: sample shape differs for {field}")
        item = {"shape": list(a.shape), **helper._norm_metrics(a, b)}
        if a.ndim and a.shape[-1] == 3:
            item["per_component"] = [
                {"component": name, **helper._norm_metrics(a[..., i], b[..., i])}
                for i, name in enumerate(("x", "y", "z"))
            ]
        sample_comparisons[field] = item
    field_gate = {
        field: {
            "relative_l2_no_phase_fit": sample_comparisons[field]["relative_l2_to_reference"],
            "threshold": THRESHOLDS["same_coordinate_complex_E_H_relative_l2_no_phase_fit"],
            "pass": sample_comparisons[field]["relative_l2_to_reference"] is not None
            and sample_comparisons[field]["relative_l2_to_reference"] <= THRESHOLDS["same_coordinate_complex_E_H_relative_l2_no_phase_fit"],
        }
        for field in ("E_V_per_m", "H_A_per_m")
    }
    all_three_groups_pass = (
        all(x["pass"] for x in global_metrics.values())
        and all(channel_gate.values())
        and boundary_gate["pass"]
        and all(x["pass"] for x in field_gate.values())
    )
    report = {
        "reference": reference["label"],
        "candidate": candidate["label"],
        "candidate_K": candidate["K"],
        "scope": "candidate K rectangle versus saved D15-Y3 finite R13 parent; candidate modal vectors zero-extended over the full 612 parent signed-key set",
        "mode_identity": {
            "candidate_active_count": candidate["modes"]["active_count"],
            "expected_formula_count": expected_count,
            "candidate_mode_sha256": candidate["modes"]["active_sha256"],
            "reference_parent_count": 612,
            "reference_parent_sha256": PARENT_MODE_SHA,
            "candidate_signed_keys_subset_of_reference": True,
            "common_key_identity_fields_exact": list(IDENTITY_FIELDS),
            "common_key_identity_mismatch_count": 0,
            "omitted_reference_key_count": len(omitted_indices),
            "selected_parent_indices_sha256": candidate["modes"]["selected_parent_indices_sha256"],
            "selected_signed_keys_sha256": candidate["modes"]["selected_signed_keys_sha256"],
        },
        "global_observables": global_metrics,
        "per_channel_R_T_zero_extended_over_612_parent_keys": mode_groups,
        "per_channel_gate": {
            "threshold": THRESHOLDS["per_channel_R_T_absolute_all_parent_modes"],
            **channel_gate,
            "all_612_R_max": all_modes["R"],
            "all_612_T_max": all_modes["T"],
            "power_carrying_R_max": power_carrying["R"],
            "power_carrying_T_max": power_carrying["T"],
            "propagating_R_diagnostic": mode_groups["propagating"]["R"],
            "propagating_T_diagnostic": mode_groups["propagating"]["T"],
        },
        "omitted_parent_tail": {
            "mode_count": len(omitted_indices),
            "propagating_count": int(np.count_nonzero(class_masks["propagating"][omitted_indices])),
            "power_carrying_count": int(np.count_nonzero(class_masks["power_carrying"][omitted_indices])),
            "power_carrying_but_not_propagating_count": int(np.count_nonzero(class_masks["power_carrying_but_not_propagating"][omitted_indices])),
            "sum_parent_R": float(np.sum(parent_r[omitted_indices])),
            "sum_parent_T": float(np.sum(parent_t[omitted_indices])),
            "sum_parent_modal_power_code_units": float(sum(float(parent_rows[int(i)]["modal_power_code_units"]) for i in omitted_indices)),
            "boundary_amplitude_l2": tail_boundary_l2,
            "boundary_amplitude_max_abs": tail_boundary_max,
            "boundary_amplitude_relative_l2_to_full_parent": tail_boundary_l2 / float(np.linalg.norm(parent_boundary)) if np.linalg.norm(parent_boundary) else None,
            "top_10_boundary_amplitudes": [
                {"key": list(parent_keys[int(omitted_indices[j])]), "abs_amplitude": float(abs(omitted_boundary[j]))}
                for j in np.argsort(np.abs(omitted_boundary))[::-1][:10]
            ],
        },
        "boundary_complex_amplitude_gate": boundary_gate,
        "same_coordinate_field_gates": field_gate,
        "same_coordinate_sample_diagnostics": {
            "coordinates": coordinate_checks,
            "fields": sample_comparisons,
            "reference_sample_archive_sha256": reference["sample_npz_sha256"],
            "candidate_sample_archive_sha256": candidate["sample_npz_sha256"],
            "no_interpolation": True,
            "phase_fit": False,
        },
        "all_three_comparison_groups_pass": bool(all_three_groups_pass),
    }
    csv_rows = []
    for i, key in enumerate(parent_keys):
        ref = parent_rows[i]
        cand = candidate_by_key.get(key)
        ref_boundary = complex_value(ref["outgoing_amplitude_at_boundary"])
        cand_boundary = complex_value(cand["outgoing_amplitude_at_boundary"]) if cand else 0.0j
        csv_rows.append({
            "candidate": candidate["label"],
            "K": candidate["K"],
            "parent_auxiliary_index": int(ref["auxiliary_index"]),
            "side": key[0],
            "direction": key[1],
            "m": key[2],
            "n": key[3],
            "polarization": key[4],
            "medium": ref["medium"],
            "propagating": bool(ref["propagating"]),
            "power_carrying": bool(ref["power_carrying"]),
            "candidate_present": cand is not None,
            "R_reference": float(ref["R"]),
            "R_candidate_zero_extended": float(cand["R"]) if cand else 0.0,
            "delta_R": float(delta_r[i]),
            "T_reference": float(ref["T"]),
            "T_candidate_zero_extended": float(cand["T"]) if cand else 0.0,
            "delta_T": float(delta_t[i]),
            "reference_modal_power_code_units": float(ref["modal_power_code_units"]),
            "candidate_modal_power_code_units_zero_extended": float(cand["modal_power_code_units"]) if cand else 0.0,
            "boundary_reference_re": ref_boundary.real,
            "boundary_reference_im": ref_boundary.imag,
            "boundary_candidate_re_zero_extended": cand_boundary.real,
            "boundary_candidate_im_zero_extended": cand_boundary.imag,
            "boundary_delta_abs": abs(cand_boundary - ref_boundary),
        })
    return report, csv_rows


def main() -> None:
    helper = helper_module()
    cases = {label: load_case(label, spec, helper) for label, spec in CASES.items()}
    reference = cases["Y3_R13_612"]
    if any(case["physical_model_sha256"] != PHYSICAL_SHA for case in cases.values()):
        raise ValueError("a case does not use the frozen D15-Y3 physical model")
    if any(case["mesh"]["axis_sha256_le_f64"] != AXIS_SHA or case["mesh"]["axis_cell_counts"] != [6, 10, 6] for case in cases.values()):
        raise ValueError("a case does not use the frozen D15-Y3 mesh")
    if any(case["quadrature"]["surface_degree"] != 28 for case in cases.values()):
        raise ValueError("a case does not use the frozen surface q28")
    if any(case["cutoff"]["policy"] != "scale_homogeneous_relative_only_v1" or case["cutoff"]["relative_tolerance"] != 1e-13 for case in cases.values()):
        raise ValueError("a case does not use the frozen relative-only cutoff policy")
    ref_keys = {helper._key(row) for row in reference["modal_orders"]}
    if len(ref_keys) != 612 or reference["modes"]["active_sha256"] != PARENT_MODE_SHA:
        raise ValueError("saved Y3 comparison parent is not the complete 612-mode finite R13 reference")
    for k in range(1, 5):
        label = f"K{k}"
        candidate = cases[label]
        if candidate["K"] != k:
            raise ValueError(f"{label}: incorrect requested rectangle")
        if candidate["source_sha"] != "b4df11e06fd02be27b33df1f432123203ac5009f":
            raise ValueError(f"{label}: K run source identity mismatch")
    # Verify that the numerical solver/action/port/runner files are unchanged between
    # the parent source and the K source; profile additions only supply the new route.
    import subprocess
    changed_core = subprocess.check_output(
        ["git", "diff", "--name-only", CASES["Y3_R13_612"]["source_sha"], CASES["K1"]["source_sha"], "--", *CORE_NUMERICAL_FILES],
        cwd=REPO,
        text=True,
    ).splitlines()
    if changed_core:
        raise ValueError(f"numerical solver/action files changed between reference and K source: {changed_core}")

    pairwise = {}
    all_csv_rows = []
    for k in range(1, 5):
        label = f"K{k}"
        pair_report, csv_rows = compare_one(reference, cases[label], helper)
        pairwise[label] = pair_report
        all_csv_rows.extend(csv_rows)

    RECORDS.mkdir(parents=True, exist_ok=True)
    csv_fields = list(all_csv_rows[0])
    with CSV_PATH.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=csv_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_csv_rows)
    csv_sha = sha_bytes(CSV_PATH.read_bytes())
    script_sha = sha_bytes(Path(__file__).read_bytes())
    report = {
        "schema": "task40.d15.y3.modal_truncation_vs_finite_r13.v1",
        "created_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "scope": "four separately completed p6-direct modal rectangles on the unchanged D15-Y3 [6,10,6] mesh, compared offline against the saved finite R13 612-mode Y3 parent; no FE, factorization, VTU, or resource-stream reads",
        "authorization": "All K=1,2,3,4 full solves were explicitly authorized and executed serially; every K ran even though earlier cases could already be compared.",
        "thresholds": THRESHOLDS,
        "reference_identity": {
            "label": reference["display"],
            "run": reference["run"],
            "source_sha": reference["source_sha"],
            "input_sha256": reference["input_sha256"],
            "physical_model_sha256": reference["physical_model_sha256"],
            "resolved_config_sha256": reference["resolved_config_sha256"],
            "mode_count": reference["modes"]["active_count"],
            "mode_sha256": reference["modes"]["active_sha256"],
            "mesh": reference["mesh"],
            "quadrature": reference["quadrature"],
            "cutoff": reference["cutoff"],
        },
        "identity_checks": {
            "all_cases_same_physical_sha": len({case["physical_model_sha256"] for case in cases.values()}) == 1,
            "all_cases_same_y3_axis_hashes": all(case["mesh"]["axis_sha256_le_f64"] == AXIS_SHA for case in cases.values()),
            "all_cases_same_mesh_counts": all(case["mesh"]["axis_cell_counts"] == [6, 10, 6] and case["mesh"]["actual_global_cell_count"] == 360 for case in cases.values()),
            "all_cases_same_surface_q28": all(case["quadrature"]["surface_degree"] == 28 for case in cases.values()),
            "all_cases_same_q15_default_volume_records": all(case["quadrature"]["volume_records"] == reference["quadrature"]["volume_records"] for case in cases.values()),
            "all_cases_same_relative_only_cutoff_policy": all(case["cutoff"]["policy"] == "scale_homogeneous_relative_only_v1" and case["cutoff"]["relative_tolerance"] == 1e-13 for case in cases.values()),
            "K_rectangles_counts": {f"K{k}": cases[f"K{k}"]["modes"]["active_count"] for k in range(1, 5)},
            "K_active_mode_sha256": {f"K{k}": cases[f"K{k}"]["modes"]["active_sha256"] for k in range(1, 5)},
            "K_selected_parent_indices_sha256": {f"K{k}": cases[f"K{k}"]["modes"]["selected_parent_indices_sha256"] for k in range(1, 5)},
            "Y3_parent_to_K_numerical_core_files_changed": changed_core,
            "source_note": "The reference and K runs have different source commits because the K profile routes were added. The inspected p6 direct solver, p6 cell action, fullspace DtN action, dtn_port_3d, and physical retained-condensed runner files are byte-identical between the two commits; per-key dispersion, beta, boundary phase, polarization, medium, and power-class fields are also exact on every common signed key.",
        },
        "cases": {
            label: {
                key: value
                for key, value in case.items()
                if key not in ("modal_orders", "auxiliary_rows", "samples")
            }
            for label, case in cases.items()
        },
        "comparisons": pairwise,
        "limitations": [
            "The parent is the saved finite R13 rectangle, not an infinite-DtN or continuum reference; FULL_DTN_NOT_VERIFIED remains.",
            "Canonical sidewall Et/Ht is NOT_MEASURED. E_t_interface/H_t_interface are retained only as the saved horizontal-interface diagnostics.",
            "Same-coordinate E/H comparisons cover the saved common sample grid only, not a whole-domain field norm; no interpolation or phase fit was used.",
            "For each K, candidate modal powers and boundary amplitudes are zero-extended over all 612 signed parent keys. Omitted-parent tail power and boundary amplitude are reported separately.",
            "Mode rectangle reduction changes the DtN operator. These comparisons do not imply accuracy outside the finite R13 reference or establish omitted-channel coupling.",
        ],
        "csv": {
            "path": str(CSV_PATH.relative_to(REPO)),
            "rows_excluding_header": len(all_csv_rows),
            "rows_per_K": 612,
            "covers_all_612_parent_keys_for_each_K": True,
            "zero_extension_for_missing_candidate_modes": True,
            "sha256": csv_sha,
        },
        "analysis_script": {
            "path": str(Path(__file__).resolve().relative_to(REPO)),
            "sha256": script_sha,
        },
    }
    JSON_PATH.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False, default=json_default) + "\n", encoding="utf-8")
    print(json.dumps({
        "json": str(JSON_PATH.relative_to(REPO)),
        "json_sha256": sha_bytes(JSON_PATH.read_bytes()),
        "csv": str(CSV_PATH.relative_to(REPO)),
        "csv_sha256": csv_sha,
        "csv_rows": len(all_csv_rows),
        "all_three_threshold_groups_pass": {label: value["all_three_comparison_groups_pass"] for label, value in pairwise.items()},
        "max_deltas": {
            label: {
                "global": {name: item["absolute_delta"] for name, item in value["global_observables"].items()},
                "all612_max_dR": value["per_channel_gate"]["all_612_R_max"]["max_abs_delta"],
                "all612_max_dT": value["per_channel_gate"]["all_612_T_max"]["max_abs_delta"],
                "power_max_dR": value["per_channel_gate"]["power_carrying_R_max"]["max_abs_delta"],
                "power_max_dT": value["per_channel_gate"]["power_carrying_T_max"]["max_abs_delta"],
                "boundary_relative": value["boundary_complex_amplitude_gate"]["relative_l2_no_phase_fit"],
                "E_relative": value["same_coordinate_field_gates"]["E_V_per_m"]["relative_l2_no_phase_fit"],
                "H_relative": value["same_coordinate_field_gates"]["H_A_per_m"]["relative_l2_no_phase_fit"],
            }
            for label, value in pairwise.items()
        },
    }, sort_keys=True))


if __name__ == "__main__":
    main()
