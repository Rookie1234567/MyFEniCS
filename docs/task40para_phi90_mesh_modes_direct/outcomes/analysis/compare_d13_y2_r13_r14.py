"""Offline compare the same-Y2 D13 R13 and R14 completed direct runs.

Reads only compact JSON/CSV artifacts and the two small reference-sample NPZs.
It does not read VTU files or resource streams and does not invoke FE code.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[4]
RESULTS = REPO / "results/si_block_phi90_50x50_17x20_h120"
OUT = REPO / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
JSON_OUT = OUT / "d13_y2_r13_r14_same_mesh_mode_expansion_v1.json"
CSV_OUT = OUT / "d13_y2_r13_r14_all_836_modes_v1.csv"
MODE_R13_SHA = "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
MODE_R14_SHA = "deefaa839044a2542560b60b68a457c4f127eee2221d6dd8477c3d49fb1a860e"
CUTOFF_POLICY = "scale_homogeneous_relative_only_v1"
CUTOFF_TOL = 1e-13
SAMPLE_FIELDS = (
    "E_V_per_m",
    "H_A_per_m",
    "E_t_interface_V_per_m",
    "H_t_interface_A_per_m",
)
CASES = {
    "R13": {
        "directory": "task40_phi90_13p5_D13_Y2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261016T190312.893443Z",
        "source_sha": "73e2fd2c4a36c9698298235148c59aa1551d74d6",
        "input_sha256": "7908141fe455ee73a1c8f213970a5c5655095a31f6afd10ce18904367b63a994",
        "mode_count": 612,
        "mode_sha256": MODE_R13_SHA,
    },
    "R14": {
        "directory": "task40_phi90_13p5_D13_R14_from_Y2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261018T071859.358847Z",
        "source_sha": "0d42d9fd999f5df7df22709723fd91ad2c5d70b1",
        "input_sha256": "cf9bc38fe33be5f658fb58d45e40242e70f6e1ef41b95c76a61102dfdf007cb5",
        "mode_count": 836,
        "mode_sha256": MODE_R14_SHA,
    },
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> tuple[Any, str]:
    raw = path.read_bytes()
    return json.loads(raw), sha(raw)


def key(row: dict[str, Any]) -> tuple[str, str, int, int, str]:
    return (
        str(row["side"]),
        str(row["direction"]),
        int(row["m"]),
        int(row["n"]),
        str(row["polarization"]),
    )


def cvalue(value: list[float]) -> complex:
    return complex(float(value[0]), float(value[1]))


def stable_l2(value: np.ndarray) -> float:
    magnitudes = np.abs(np.asarray(value).ravel())
    if magnitudes.size == 0:
        return 0.0
    scale = float(np.max(magnitudes))
    if scale == 0.0:
        return 0.0
    return float(scale * np.sqrt(np.sum((magnitudes / scale) ** 2, dtype=np.float64)))


def array_hash(value: np.ndarray) -> str:
    return sha(np.ascontiguousarray(value).view(np.uint8).tobytes())


def delta_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    a = np.asarray(reference)
    b = np.asarray(candidate)
    if a.shape != b.shape:
        raise ValueError(f"array shape mismatch: {a.shape} != {b.shape}")
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("nonfinite comparison array")
    delta = b - a
    absolute = np.abs(delta)
    flat = int(np.argmax(absolute)) if absolute.size else 0
    na = stable_l2(a)
    nb = stable_l2(b)
    nd = stable_l2(delta)
    return {
        "shape": list(a.shape),
        "reference_l2": na,
        "candidate_l2": nb,
        "delta_l2": nd,
        "relative_l2_to_reference": nd / na if na else None,
        "relative_l2_to_candidate": nd / nb if nb else None,
        "max_abs_delta": float(np.max(absolute, initial=0.0)),
        "max_delta_flat_index": flat,
    }


def mode_map(rows: list[dict[str, Any]], label: str) -> dict[tuple[str, str, int, int, str], dict[str, Any]]:
    result: dict[tuple[str, str, int, int, str], dict[str, Any]] = {}
    for row in rows:
        k = key(row)
        if k in result:
            raise ValueError(f"{label}: duplicate mode key {k}")
        result[k] = row
    return result


def max_power_delta(
    keys: list[tuple[str, str, int, int, str]],
    rows_a: dict[tuple[str, str, int, int, str], dict[str, Any]],
    rows_b: dict[tuple[str, str, int, int, str], dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    if not keys:
        return {"count": 0, "max_abs_delta": 0.0, "max_delta_key": None, "within_1e-6": True}
    differences = np.asarray([float(rows_b[k][field]) - float(rows_a[k][field]) for k in keys])
    i = int(np.argmax(np.abs(differences)))
    maximum = float(abs(differences[i]))
    return {
        "count": len(keys),
        "max_abs_delta": maximum,
        "max_delta_signed": float(differences[i]),
        "max_delta_key": list(keys[i]),
        "delta_l2": stable_l2(differences),
        "nonzero_delta_count": int(np.count_nonzero(differences)),
        "diagnostic_gate_1e-6_pass": maximum <= 1e-6,
    }


def load_case(label: str, spec: dict[str, Any]) -> dict[str, Any]:
    run = RESULTS / spec["directory"] / spec["stamp"]
    out = run / "numerical_output"
    summary, summary_sha = read_json(run / "run_summary.json")
    manifest, manifest_sha = read_json(run / "run_manifest.json")
    phase, phase_sha = read_json(run / "workflow_phase.json")
    direct, direct_sha = read_json(run / "p6_condensed_direct_summary.json")
    resolved, resolved_sha = read_json(run / "resolved_config.json")
    power, power_sha = read_json(out / "dtn_port_power_metrics_3d.json")
    volume, volume_sha = read_json(out / "volume_absorption.json")
    modes, modes_sha = read_json(out / "dtn_port_diffraction_orders_3d.json")
    samples, samples_sha = read_json(out / "full3d_reference_samples.json")
    resource = summary["resource_authority"]
    source_sha = (run / "source_sha.txt").read_text().strip()
    input_sha = (run / "input_sha256.txt").read_text().strip()
    physical_sha = (run / "physical_model_sha256.txt").read_text().strip()
    op = direct["operator_identity"]
    phase_file_sha = sha((run / "workflow_phase.json").read_bytes())
    if summary.get("status") != "finished" or summary.get("exit_status") != 0:
        raise ValueError(f"{label}: run not naturally finished with exit 0")
    if summary.get("result_classification") != "worker_exit0":
        raise ValueError(f"{label}: expected worker_exit0 classification")
    if not resource.get("descendants_cleared") or resource.get("remaining_child_pids"):
        raise ValueError(f"{label}: process tree not cleared")
    if phase.get("phase") != "complete" or not phase.get("facts", {}).get("passed"):
        raise ValueError(f"{label}: completion gate missing")
    if not direct.get("passed") or not direct.get("complete_solve"):
        raise ValueError(f"{label}: direct numerical/energy gate not passed")
    if source_sha != spec["source_sha"] or input_sha != spec["input_sha256"]:
        raise ValueError(f"{label}: source or input identity mismatch")
    if direct["mesh_evidence"]["axis_cell_counts"] != [6, 24, 14]:
        raise ValueError(f"{label}: not the Y2 mesh")
    if power.get("active_mode_count") != spec["mode_count"] or power.get("active_mode_sha256") != spec["mode_sha256"]:
        raise ValueError(f"{label}: mode identity mismatch")
    if op.get("dtn_sparse_cutoff_policy") != CUTOFF_POLICY or op.get("dtn_sparse_cutoff_relative_tolerance") != CUTOFF_TOL:
        raise ValueError(f"{label}: sparse cutoff policy mismatch")
    if direct["production_port_mpc_witness"].get("dtn_quadrature_degree") != 28:
        raise ValueError(f"{label}: surface quadrature mismatch")
    orders = modes.get("orders")
    if not isinstance(orders, list) or len(orders) != spec["mode_count"]:
        raise ValueError(f"{label}: diffraction output row count mismatch")
    sample_path = out / "full3d_reference_samples.npz"
    if sha(sample_path.read_bytes()) != samples.get("archive_sha256"):
        raise ValueError(f"{label}: sample NPZ hash mismatch")
    totals = {
        "R_total": float(power["R_total"]),
        "R00_s": float(power["R00_s"]),
        "R00_p": float(power["R00_p"]),
        "R00_total": float(power["R00_total"]),
        "T_total": float(power["T_total"]),
        "A_balance": float(power["A_balance"]),
        "A_volume": float(volume["A_volume_total"]),
        "A_grating": float(volume["A_volume_grating"]),
        "A_substrate": float(volume["A_volume_substrate"]),
        "energy_closure_abs": abs(1.0 - float(power["R_total"]) - float(power["T_total"]) - float(volume["A_volume_total"])),
        "port_volume_closure_signed": float(volume["energy_closure_error_port_volume"]),
    }
    return {
        "label": label,
        "run": run,
        "output": out,
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_sha256": physical_sha,
        "resolved_sha256": resolved_sha,
        "resolved": resolved,
        "manifest_sha256": manifest_sha,
        "summary_sha256": summary_sha,
        "phase_sha256": phase_file_sha,
        "direct_sha256": direct_sha,
        "mode_rows": orders,
        "mode_map": mode_map(orders, label),
        "mode_count": spec["mode_count"],
        "mode_sha256": spec["mode_sha256"],
        "axis_counts": direct["mesh_evidence"]["axis_cell_counts"],
        "actual_cells": direct["mesh_evidence"]["actual_global_cell_count"],
        "axis_sha256": direct["mesh_evidence"]["axis_sha256_le_f64"],
        "cutoff_policy": op["dtn_sparse_cutoff_policy"],
        "cutoff_tolerance": op["dtn_sparse_cutoff_relative_tolerance"],
        "cutoff_identity_sha256": op["dtn_sparse_cutoff_identity_sha256"],
        "surface_q": direct["production_port_mpc_witness"]["dtn_quadrature_degree"],
        "volume_q_records": direct["operator_identity"]["volume_quadrature_records"],
        "totals": totals,
        "direct_summary": direct,
        "phase": phase,
        "power_metrics_sha256": power_sha,
        "volume_sha256": volume_sha,
        "mode_json_sha256": modes_sha,
        "sample_metadata": samples,
        "sample_metadata_sha256": samples_sha,
        "npz_path": sample_path,
        "resource": {
            "elapsed_seconds": resource["elapsed_seconds"],
            "tree_rss_peak_bytes": resource["sampled_process_tree_rss_peak_bytes"],
            "tree_swap_peak_bytes": resource["sampled_process_tree_swap_peak_bytes"],
            "job_swap_activity": resource["job_swap_activity"],
            "global_swap_activity": resource.get("global_swap_activity"),
            "pss_status": resource["pss_status"],
        },
    }


def main() -> None:
    r13 = load_case("R13", CASES["R13"])
    r14 = load_case("R14", CASES["R14"])
    if r13["physical_sha256"] != r14["physical_sha256"]:
        raise ValueError("physical model differs")
    if r13["axis_sha256"] != r14["axis_sha256"] or r13["axis_counts"] != r14["axis_counts"]:
        raise ValueError("same-Y2 mesh identity differs")
    if r13["surface_q"] != r14["surface_q"] or r13["surface_q"] != 28:
        raise ValueError("surface quadrature differs")
    if r13["volume_q_records"] != r14["volume_q_records"]:
        raise ValueError("volume quadrature records differ")
    if r13["cutoff_policy"] != r14["cutoff_policy"] or r13["cutoff_tolerance"] != r14["cutoff_tolerance"]:
        raise ValueError("sparse cutoff policy differs")
    if r13["source_sha"] == r14["source_sha"]:
        raise ValueError("expected distinct source snapshots; comparison should report this")

    keys13 = set(r13["mode_map"])
    keys14 = set(r14["mode_map"])
    common = sorted(keys13 & keys14)
    added = sorted(keys14 - keys13)
    missing = sorted(keys13 - keys14)
    if len(common) != 612 or len(added) != 224 or missing:
        raise ValueError(f"unexpected mode-set relation: common={len(common)} added={len(added)} missing={len(missing)}")

    branch_fields = ("medium", "direction", "polarization", "beta", "boundary_phase", "propagating", "power_carrying", "refractive_index")
    branch_match = True
    for k in common:
        a, b = r13["mode_map"][k], r14["mode_map"][k]
        if any(a.get(field) != b.get(field) for field in branch_fields):
            raise ValueError(f"mode branch/reference differs for common key {k}")

    common_rows13 = [r13["mode_map"][k] for k in common]
    common_rows14 = [r14["mode_map"][k] for k in common]
    amplitude_fields = ("outgoing_amplitude_at_boundary", "outgoing_amplitude", "auxiliary_amplitude_total_projection", "incident_projection")
    amplitude: dict[str, Any] = {}
    for field in amplitude_fields:
        a = np.asarray([cvalue(row[field]) for row in common_rows13], dtype=np.complex128)
        b = np.asarray([cvalue(row[field]) for row in common_rows14], dtype=np.complex128)
        metrics = delta_metrics(a, b)
        delta = b - a
        max_i = int(np.argmax(np.abs(delta))) if delta.size else 0
        metrics["max_delta_key"] = list(common[max_i]) if delta.size else None
        metrics["max_abs_delta"] = float(np.max(np.abs(delta), initial=0.0))
        metrics["relative_l2_gate_1e-4_pass"] = (
            bool(metrics["relative_l2_to_reference"] <= 1e-4)
            if metrics["relative_l2_to_reference"] is not None else None
        )
        amplitude[field] = metrics

    class_masks = {
        "all_common_612": lambda x: True,
        "propagating_common": lambda x: bool(x["propagating"]),
        "power_carrying_common": lambda x: bool(x["power_carrying"]),
        "evanescent_nonpropagating_common": lambda x: not bool(x["propagating"]),
        "non_power_carrying_common": lambda x: not bool(x["power_carrying"]),
    }
    common_power: dict[str, Any] = {}
    for cname, predicate in class_masks.items():
        subset = [k for k in common if predicate(r13["mode_map"][k])]
        common_power[cname] = {
            "count": len(subset),
            "R": max_power_delta(subset, r13["mode_map"], r14["mode_map"], "R"),
            "T": max_power_delta(subset, r13["mode_map"], r14["mode_map"], "T"),
        }

    tail_rows = [r14["mode_map"][k] for k in added]
    tail = {
        "count": len(added),
        "propagating_count": sum(bool(row["propagating"]) for row in tail_rows),
        "power_carrying_count": sum(bool(row["power_carrying"]) for row in tail_rows),
        "R_total_contribution": float(sum(float(row["R"]) for row in tail_rows)),
        "T_total_contribution": float(sum(float(row["T"]) for row in tail_rows)),
        "R_max_abs": max(
            ({"value": float(row["R"]), "key": list(key(row))} for row in tail_rows),
            key=lambda item: abs(item["value"]), default={"value": 0.0, "key": None},
        ),
        "T_max_abs": max(
            ({"value": float(row["T"]), "key": list(key(row))} for row in tail_rows),
            key=lambda item: abs(item["value"]), default={"value": 0.0, "key": None},
        ),
        "keys": [list(k) for k in added],
        "no_R13_counterpart": True,
    }

    samples: dict[str, dict[str, np.ndarray]] = {}
    for case in (r13, r14):
        with np.load(case["npz_path"], allow_pickle=False) as archive:
            arrays = {name: archive[name].copy() for name in archive.files}
        required = {"x_nm", "y_nm", "z_nm", *SAMPLE_FIELDS}
        if not required.issubset(arrays):
            raise ValueError(f"{case['label']}: incomplete reference samples")
        samples[case["label"]] = arrays
    for axis in ("x_nm", "y_nm", "z_nm"):
        if not np.array_equal(samples["R13"][axis], samples["R14"][axis]):
            raise ValueError(f"sample coordinates differ: {axis}")
    sample_metrics: dict[str, Any] = {}
    for field in SAMPLE_FIELDS:
        a, b = samples["R13"][field], samples["R14"][field]
        item = delta_metrics(a, b)
        item["dtype"] = str(a.dtype)
        item["relative_l2_gate_1e-4_on_finite_samples_pass"] = bool(item["relative_l2_to_reference"] <= 1e-4) if item["relative_l2_to_reference"] is not None else None
        if a.ndim and a.shape[-1] == 3:
            item["per_component"] = [
                {"component": component, **delta_metrics(a[..., i], b[..., i])}
                for i, component in enumerate(("x", "y", "z"))
            ]
        sample_metrics[field] = item

    global_totals: dict[str, Any] = {}
    for field in r13["totals"]:
        a, b = r13["totals"][field], r14["totals"][field]
        delta = float(b - a)
        formal_gate = field in {"R_total", "T_total", "A_balance", "A_volume"}
        global_totals[field] = {
            "R13": a,
            "R14": b,
            "delta_R14_minus_R13": delta,
            "absolute_delta": abs(delta),
            "gate_1e-5_pass": bool(abs(delta) <= 1e-5) if formal_gate else None,
        }

    r13_sums = {
        "R_sum_over_orders": float(sum(float(row["R"]) for row in r13["mode_rows"])),
        "T_sum_over_orders": float(sum(float(row["T"]) for row in r13["mode_rows"])),
    }
    r14_sums = {
        "R_sum_over_orders": float(sum(float(row["R"]) for row in r14["mode_rows"])),
        "T_sum_over_orders": float(sum(float(row["T"]) for row in r14["mode_rows"])),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    fields = [
        "side", "direction", "m", "n", "polarization", "in_R13", "in_R14",
        "propagating", "power_carrying", "medium", "beta_re", "beta_im",
        "boundary_phase_re", "boundary_phase_im",
        "R13_boundary_re", "R13_boundary_im", "R14_boundary_re", "R14_boundary_im",
        "delta_boundary_abs", "R13_R", "R14_R", "delta_R", "R13_T", "R14_T", "delta_T",
    ]
    with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for k in sorted(keys13 | keys14):
            a = r13["mode_map"].get(k)
            b = r14["mode_map"].get(k)
            ref = b if b is not None else a
            assert ref is not None
            row: dict[str, Any] = {
                "side": k[0], "direction": k[1], "m": k[2], "n": k[3], "polarization": k[4],
                "in_R13": a is not None, "in_R14": b is not None,
                "propagating": bool(ref["propagating"]), "power_carrying": bool(ref["power_carrying"]),
                "medium": ref["medium"], "beta_re": cvalue(ref["beta"]).real, "beta_im": cvalue(ref["beta"]).imag,
                "boundary_phase_re": cvalue(ref["boundary_phase"]).real, "boundary_phase_im": cvalue(ref["boundary_phase"]).imag,
            }
            if a is not None:
                va = cvalue(a["outgoing_amplitude_at_boundary"])
                row["R13_boundary_re"], row["R13_boundary_im"] = va.real, va.imag
                row["R13_R"], row["R13_T"] = float(a["R"]), float(a["T"])
            if b is not None:
                vb = cvalue(b["outgoing_amplitude_at_boundary"])
                row["R14_boundary_re"], row["R14_boundary_im"] = vb.real, vb.imag
                row["R14_R"], row["R14_T"] = float(b["R"]), float(b["T"])
            if a is not None and b is not None:
                row["delta_boundary_abs"] = abs(cvalue(b["outgoing_amplitude_at_boundary"]) - cvalue(a["outgoing_amplitude_at_boundary"]))
                row["delta_R"] = float(b["R"]) - float(a["R"])
                row["delta_T"] = float(b["T"]) - float(a["T"])
            writer.writerow(row)

    csv_sha = sha(CSV_OUT.read_bytes())
    report = {
        "schema": "task40.d13.y2.r13_r14_same_mesh_mode_expansion_comparison.v1",
        "scope": "offline comparison of naturally completed R13 and R14 runs on the same Y2 mesh; no FE, factor, VTU, or resource-stream reads",
        "identity": {
            label: {
                "run_directory": str(case["run"]),
                "source_sha": case["source_sha"],
                "input_sha256": case["input_sha256"],
                "physical_model_sha256": case["physical_sha256"],
                "resolved_config_sha256": case["resolved_sha256"],
                "run_manifest_sha256": case["manifest_sha256"],
                "run_summary_sha256": case["summary_sha256"],
                "workflow_phase_sha256": case["phase_sha256"],
                "direct_summary_sha256": case["direct_sha256"],
                "active_mode_count": case["mode_count"],
                "active_mode_sha256": case["mode_sha256"],
                "axis_cell_counts": case["axis_counts"],
                "actual_cells": case["actual_cells"],
                "axis_sha256_le_f64": case["axis_sha256"],
                "surface_quadrature_degree": case["surface_q"],
                "volume_quadrature_records": case["volume_q_records"],
                "cutoff_policy": case["cutoff_policy"],
                "cutoff_relative_tolerance": case["cutoff_tolerance"],
                "cutoff_identity_sha256": case["cutoff_identity_sha256"],
                "sample_artifact_hashes": {
                    "modes_json": case["mode_json_sha256"],
                    "power_metrics_json": case["power_metrics_sha256"],
                    "volume_absorption_json": case["volume_sha256"],
                    "sample_metadata_json": case["sample_metadata_sha256"],
                    "sample_npz": case["sample_metadata"]["archive_sha256"],
                },
                "qualification_status": case["direct_summary"]["status"],
                "full_dtn_status": case["direct_summary"]["full_dtn_status"],
            }
            for label, case in (("R13", r13), ("R14", r14))
        },
        "same_mesh_and_material_checks": {
            "physical_model_sha_equal": r13["physical_sha256"] == r14["physical_sha256"],
            "same_axis_counts": r13["axis_counts"] == r14["axis_counts"],
            "same_axis_hashes": r13["axis_sha256"] == r14["axis_sha256"],
            "same_surface_quadrature_q28": r13["surface_q"] == r14["surface_q"] == 28,
            "same_volume_quadrature_records": r13["volume_q_records"] == r14["volume_q_records"],
            "same_relative_only_sparse_policy": r13["cutoff_policy"] == r14["cutoff_policy"] == CUTOFF_POLICY and r13["cutoff_tolerance"] == r14["cutoff_tolerance"] == CUTOFF_TOL,
            "source_sha_equal": False,
            "source_sha_note": "R13 and R14 are distinct frozen source snapshots; the pair is same physical model, mesh axes, volume/surface quadrature, and sparse-cutoff policy, but not source-identical.",
        },
        "mode_set_relation": {
            "R13_count": len(keys13),
            "R14_count": len(keys14),
            "common_count": len(common),
            "R14_added_count": len(added),
            "R13_missing_from_R14_count": len(missing),
            "common_mode_branch_beta_phase_exact": branch_match,
            "R13_common_modes_subset_of_R14": not missing and len(common) == len(keys13),
            "parent_rectangles": {"R13": [-4, 4, -8, 8], "R14": [-5, 5, -9, 9]},
            "no_phase_fit": True,
        },
        "global_observable_differences": global_totals,
        "common_mode_complex_amplitude_differences": amplitude,
        "common_mode_per_order_power_differences": common_power,
        "R14_new_224_mode_tail": tail,
        "per_order_total_consistency": {
            "R13": {**r13_sums, "R_total_reported": r13["totals"]["R_total"], "T_total_reported": r13["totals"]["T_total"]},
            "R14": {**r14_sums, "R_total_reported": r14["totals"]["R_total"], "T_total_reported": r14["totals"]["T_total"]},
        },
        "same_coordinate_saved_field_samples": {
            "coordinates": {axis: {"shape": list(samples["R13"][axis].shape), "sha256": array_hash(samples["R13"][axis])} for axis in ("x_nm", "y_nm", "z_nm")},
            "R13_R14_coordinates_equal": True,
            "metrics": sample_metrics,
            "phase_fit": False,
            "scope_note": "Finite saved sample points only; E_t/H_t arrays are horizontal interface z-plane samples, not canonical pillar-sidewall traces; no full-domain norm is claimed.",
        },
        "solver_and_resource": {
            label: {
                "condensed_direct_relative": case["direct_summary"]["residuals"]["condensed_direct_relative"],
                "condensed_gate": case["direct_summary"]["residuals"]["condensed_direct_residual_gate"],
                "original_A6_active_rectangle_relative": case["direct_summary"]["residuals"]["original_A6_active_rectangle_relative"],
                "original_A6_gate": case["direct_summary"]["residuals"]["original_A6_active_rectangle_relative_gate"],
                "same_factor_corrections": case["direct_summary"]["factor"]["same_factor_correction_count"],
                "factor": {k: case["direct_summary"]["factor"].get(k) for k in ("symbolic_calls", "numeric_calls", "solve_calls", "solve_lifecycle_wall_seconds")},
                "matrix": {
                    "shape": case["direct_summary"]["matrix"].get("shape"),
                    **{
                        k: case["direct_summary"]["matrix"].get("actual_matrix_info_after_solve", {}).get(k)
                        for k in ("nz_used", "nz_allocated")
                    },
                },
                "resource": case["resource"],
            }
            for label, case in (("R13", r13), ("R14", r14))
        },
        "limits": [
            "This isolates a finite R13-to-R14 mode-rectangle expansion on the same Y2 mesh; it is not a mesh convergence test.",
            "The R14 added 224 modes have no R13 solution counterpart; their R14 power is reported as a tail contribution, not as a delta from zero.",
            "Both runs remain AUTHORITY_LIMITED and FULL_DTN_NOT_VERIFIED; the finite rectangle is not a full-DtN qualification.",
            "Sampled E/H comparisons use the stored common coordinates and no phase fit; they are not full-domain norms.",
            "Canonical pillar-sidewall Et/Ht remains NOT_MEASURED; horizontal z-plane tangential samples are not substituted for it.",
            "The pre-release six-key witness remains OBSERVED_NOT_QUALIFICATION and is not promoted to a solver gate.",
        ],
        "csv": {"path": str(CSV_OUT.relative_to(REPO)), "rows_excluding_header": 836, "sha256": csv_sha},
        "script": {"path": str(Path(__file__).resolve().relative_to(REPO)), "sha256": sha(Path(__file__).read_bytes())},
    }
    JSON_OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(JSON_OUT.relative_to(REPO)), "json_sha256": sha(JSON_OUT.read_bytes()), "csv": str(CSV_OUT.relative_to(REPO)), "csv_sha256": csv_sha, "common": len(common), "added": len(added)}, sort_keys=True))


if __name__ == "__main__":
    main()
