"""Offline compare of same-relative-only Y2 and Z2 terminal outputs; no FE/VTU/resources."""
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
JSON_OUT = OUT / "d13_y2_z2_same_relative_only_comparison_v1.json"
CSV_OUT = OUT / "d13_y2_z2_same_relative_only_all_612_modes_v1.csv"
MODE_SHA = "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
CASES = {
    "Y2": {
        "directory": "task40_phi90_13p5_D13_Y2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261016T190312.893443Z",
        "source_sha": "73e2fd2c4a36c9698298235148c59aa1551d74d6",
        "input_sha256": "7908141fe455ee73a1c8f213970a5c5655095a31f6afd10ce18904367b63a994",
        "axes": [6, 24, 14],
    },
    "Z2": {
        "directory": "task40_phi90_13p5_D13_Z2_from_Y2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261018T040538.010965Z",
        "source_sha": "2aa5558f7c1472df3d3ac6161244e689a959da73",
        "input_sha256": "32eae0338865ad3784bc9d835b5fb21ca27ea525529e12be0688317b49048309",
        "axes": [6, 24, 28],
    },
}
SAMPLE_FIELDS = (
    "E_V_per_m", "H_A_per_m", "E_t_interface_V_per_m", "H_t_interface_A_per_m",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> tuple[Any, str]:
    data = path.read_bytes()
    return json.loads(data), sha(data)


def array_sha(value: np.ndarray) -> str:
    return sha(np.ascontiguousarray(value).view(np.uint8).tobytes())


def complex_value(pair: list[float]) -> complex:
    return complex(float(pair[0]), float(pair[1]))


def key(row: dict[str, Any]) -> tuple[str, str, int, int, str]:
    return (str(row["side"]), str(row["direction"]), int(row["m"]), int(row["n"]), str(row["polarization"]))


def diff_paths(a: Any, b: Any, prefix: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            p = f"{prefix}.{k}" if prefix else k
            if k not in a or k not in b:
                out.append(p)
            else:
                out.extend(diff_paths(a[k], b[k], p))
        return out
    return [] if a == b else [prefix]


def norm_metrics(a: np.ndarray, b: np.ndarray) -> dict[str, Any]:
    delta = np.asarray(b) - np.asarray(a)
    na = float(np.linalg.norm(np.asarray(a).ravel()))
    nb = float(np.linalg.norm(np.asarray(b).ravel()))
    nd = float(np.linalg.norm(delta.ravel()))
    flat_i = int(np.argmax(np.abs(delta))) if delta.size else 0
    return {
        "reference_l2_Y2": na,
        "candidate_l2_Z2": nb,
        "delta_l2": nd,
        "relative_l2_to_Y2": nd / na if na else None,
        "relative_l2_to_Z2": nd / nb if nb else None,
        "max_abs_delta": float(np.max(np.abs(delta), initial=0.0)),
        "max_delta_index": [int(i) for i in np.unravel_index(flat_i, delta.shape)] if delta.size else [],
    }


def load_case(label: str, spec: dict[str, Any]) -> dict[str, Any]:
    run = RESULTS / spec["directory"] / spec["stamp"]
    out = run / "numerical_output"
    summary, summary_sha = read_json(run / "run_summary.json")
    _manifest, manifest_sha = read_json(run / "run_manifest.json")
    _phase, phase_sha = read_json(run / "workflow_phase.json")
    direct, direct_sha = read_json(run / "p6_condensed_direct_summary.json")
    resolved, resolved_sha = read_json(run / "resolved_config.json")
    power, power_sha = read_json(out / "dtn_port_power_metrics_3d.json")
    volume, volume_sha = read_json(out / "volume_absorption.json")
    modes, modes_sha = read_json(out / "dtn_port_diffraction_orders_3d.json")
    auxiliary, aux_sha = read_json(out / "dtn_auxiliary_amplitudes_3d.json")
    sample_meta, sample_meta_sha = read_json(out / "full3d_reference_samples.json")
    resource = summary["resource_authority"]
    source_sha = (run / "source_sha.txt").read_text().strip()
    input_sha = (run / "input_sha256.txt").read_text().strip()
    physical_sha = (run / "physical_model_sha256.txt").read_text().strip()
    op = direct["direct_factor_evidence"]["operator_identity"]
    if summary.get("result_classification") != "worker_exit0" or summary.get("exit_status") != 0:
        raise ValueError(f"{label}: run not worker_exit0")
    if not resource.get("descendants_cleared") or resource.get("remaining_child_pids"):
        raise ValueError(f"{label}: process tree not cleared")
    if not direct.get("passed") or not direct.get("complete_solve"):
        raise ValueError(f"{label}: direct solve not passed")
    if source_sha != spec["source_sha"] or input_sha != spec["input_sha256"]:
        raise ValueError(f"{label}: source/input identity mismatch")
    if power.get("active_mode_count") != 612 or power.get("active_mode_sha256") != MODE_SHA:
        raise ValueError(f"{label}: active mode identity mismatch")
    if len(modes.get("orders", [])) != 612 or len(auxiliary) != 612:
        raise ValueError(f"{label}: expected 612 mode and auxiliary rows")
    if [int(x["auxiliary_index"]) for x in modes["orders"]] != list(range(612)):
        raise ValueError(f"{label}: modal output order mismatch")
    if [int(x["auxiliary_index"]) for x in auxiliary] != list(range(612)):
        raise ValueError(f"{label}: auxiliary output order mismatch")
    if direct["mesh_evidence"]["axis_cell_counts"] != spec["axes"]:
        raise ValueError(f"{label}: axis counts mismatch")
    if direct["production_port_mpc_witness"]["dtn_quadrature_degree"] != 28:
        raise ValueError(f"{label}: surface q mismatch")
    if op["dtn_sparse_cutoff_policy"] != "scale_homogeneous_relative_only_v1" or op["dtn_sparse_cutoff_relative_tolerance"] != 1e-13:
        raise ValueError(f"{label}: cutoff contract mismatch")
    if sample_meta["archive_bytes"] != (out / "full3d_reference_samples.npz").stat().st_size:
        raise ValueError(f"{label}: sample archive size mismatch")
    totals = {
        "R_total": float(power["R_total"]),
        "R00_s": float(power["R00_s"]),
        "R00_p": float(power["R00_p"]),
        "R00_total": float(power["R00_total"]),
        "T_total": float(power["T_total"]),
        "A_balance": float(power["A_balance"]),
        "A_volume": float(volume["A_volume_total"]),
        "A_grating": float(volume["A_grating"]),
        "A_substrate": float(volume["A_substrate"]),
        "energy_closure_abs": abs(1.0 - float(power["R_total"]) - float(power["T_total"]) - float(volume["A_volume_total"])),
        "port_volume_closure_signed": float(volume["energy_closure_error_port_volume"]),
    }
    return {
        "label": label, "run": run, "output": out,
        "source_sha": source_sha, "input_sha256": input_sha, "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha, "resolved_config": resolved,
        "manifest_sha256": manifest_sha, "run_summary_sha256": summary_sha,
        "phase_sha256": phase_sha, "direct_summary_sha256": direct_sha,
        "qualification_status": direct["status"], "full_dtn_status": direct["full_dtn_status"],
        "mode_rows": modes["orders"], "aux_rows": auxiliary,
        "mode_count": 612, "mode_sha256": MODE_SHA,
        "axes": direct["mesh_evidence"]["axis_cell_counts"],
        "actual_cells": direct["mesh_evidence"]["actual_global_cell_count"],
        "axis_sha256_le_f64": direct["mesh_evidence"]["axis_sha256_le_f64"],
        "cutoff_policy": op["dtn_sparse_cutoff_policy"],
        "cutoff_relative_tolerance": op["dtn_sparse_cutoff_relative_tolerance"],
        "cutoff_identity_sha256": op["dtn_sparse_cutoff_identity_sha256"],
        "surface_q": direct["production_port_mpc_witness"]["dtn_quadrature_degree"],
        "volume_q_records": direct["operator_identity"]["volume_quadrature_records"],
        "totals": totals,
        "solver": direct["residuals"],
        "factor": direct["factor"],
        "matrix_info": direct["matrix"].get("actual_matrix_info_after_solve", {}),
        "resource": {
            "elapsed_seconds": resource["elapsed_seconds"],
            "tree_rss_peak_bytes": resource["sampled_process_tree_rss_peak_bytes"],
            "tree_swap_peak_bytes": resource["sampled_process_tree_swap_peak_bytes"],
            "global_swap_activity_unattributed": resource.get("global_swap_activity"),
            "pss_status": resource["pss_status"],
        },
        "sample_meta": sample_meta,
        "npz_path": out / "full3d_reference_samples.npz",
        "sample_artifacts": {"power_metrics_sha256": power_sha, "volume_sha256": volume_sha,
            "modes_sha256": modes_sha, "auxiliary_sha256": aux_sha,
            "sample_meta_sha256": sample_meta_sha},
    }


def amplitude_comparison(a_rows: list[dict[str, Any]], b_rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys_a, keys_b = [key(x) for x in a_rows], [key(x) for x in b_rows]
    if keys_a != keys_b:
        raise ValueError("ordered mode keys differ")
    branch_fields = ("medium", "direction", "polarization", "beta", "boundary_phase", "propagating", "power_carrying", "refractive_index")
    for i, (a, b) in enumerate(zip(a_rows, b_rows, strict=True)):
        if any(a[f] != b[f] for f in branch_fields):
            raise ValueError(f"mode reference/branch differs at {i}: {keys_a[i]}")
    fields = ("outgoing_amplitude", "outgoing_amplitude_at_boundary", "auxiliary_amplitude_total_projection")
    result: dict[str, Any] = {}
    arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for field in fields:
        a = np.asarray([complex_value(row[field]) for row in a_rows], dtype=np.complex128)
        b = np.asarray([complex_value(row[field]) for row in b_rows], dtype=np.complex128)
        d = b - a
        top = np.argsort(np.abs(d))[::-1][:10]
        result[field] = {
            **norm_metrics(a, b),
            "max_delta_key": list(keys_a[int(np.argmax(np.abs(d)))]) if d.size else None,
            "top_10_absolute_deltas": [{"key": list(keys_a[int(i)]), "abs_delta": float(abs(d[int(i)]))} for i in top],
        }
        arrays[field] = (a, b)
    classes = {
        "all_612": np.ones(612, dtype=bool),
        "propagating": np.asarray([bool(x["propagating"]) for x in a_rows]),
        "power_carrying": np.asarray([bool(x["power_carrying"]) for x in a_rows]),
        "evanescent_nonpropagating": np.asarray([not bool(x["propagating"]) for x in a_rows]),
        "non_power_carrying": np.asarray([not bool(x["power_carrying"]) for x in a_rows]),
    }
    powers: dict[str, Any] = {}
    for cname, mask in classes.items():
        ix = np.flatnonzero(mask)
        powers[cname] = {"count": int(ix.size)}
        for field in ("R", "T", "modal_power_code_units", "power_ratio"):
            va = np.asarray([float(a_rows[int(i)][field]) for i in ix])
            vb = np.asarray([float(b_rows[int(i)][field]) for i in ix])
            delta = vb - va
            j = int(np.argmax(np.abs(delta))) if delta.size else 0
            mx = float(np.max(np.abs(delta), initial=0.0))
            powers[cname][field] = {
                "delta_l2": float(np.linalg.norm(delta)),
                "max_abs_delta": mx,
                "max_delta_key": list(keys_a[int(ix[j])]) if delta.size else None,
                "nonzero_delta_count": int(np.count_nonzero(delta)),
                "within_1e-6_diagnostic": bool(mx <= 1e-6),
            }
    boundary = result["outgoing_amplitude_at_boundary"]
    boundary["formal_relative_l2_gate_1e-4_pass"] = (
        bool(boundary["relative_l2_to_Y2"] <= 1e-4)
        if boundary["relative_l2_to_Y2"] is not None else None
    )
    return {"all_612_keys_order_branch_phase_exact": True, "complex_amplitudes": result,
            "formal_gate_scope": {"complex_amplitude_field": "outgoing_amplitude_at_boundary",
                "threshold": 1e-4, "no_phase_fit": True,
                "raw_outgoing_coefficient_and_auxiliary_projection_are_diagnostics_only": True},
            "per_mode_power": powers,
            "mode_threshold_note": "Formal Task40 per-mode R/T gate is all propagating modes <=1e-6; all_612 and power_carrying results are separately reported, including lossy nonpropagating-but-power-carrying modes."}


def load_samples(case: dict[str, Any]) -> dict[str, np.ndarray]:
    raw = case["npz_path"].read_bytes()
    if sha(raw) != case["sample_meta"]["archive_sha256"]:
        raise ValueError(f"{case['label']}: sample NPZ hash mismatch")
    with np.load(case["npz_path"], allow_pickle=False) as z:
        arrays = {k: z[k].copy() for k in z.files}
    required = {"x_nm", "y_nm", "z_nm", *SAMPLE_FIELDS}
    if not required.issubset(arrays):
        raise ValueError(f"{case['label']}: incomplete sample arrays")
    return arrays


def main() -> None:
    y2 = load_case("Y2", CASES["Y2"])
    z2 = load_case("Z2", CASES["Z2"])
    if y2["mode_sha256"] != z2["mode_sha256"] or y2["cutoff_identity_sha256"] != z2["cutoff_identity_sha256"]:
        raise ValueError("mode or cutoff identity differs")
    if y2["cutoff_policy"] != z2["cutoff_policy"] or y2["cutoff_relative_tolerance"] != z2["cutoff_relative_tolerance"]:
        raise ValueError("sparse cutoff contract differs")
    if y2["surface_q"] != z2["surface_q"] or y2["surface_q"] != 28:
        raise ValueError("surface quadrature differs")
    if y2["volume_q_records"] != z2["volume_q_records"]:
        raise ValueError("volume quadrature records differ")
    axes_a, axes_b = y2["axis_sha256_le_f64"], z2["axis_sha256_le_f64"]
    if axes_a["x"] != axes_b["x"] or axes_a["y"] != axes_b["y"] or axes_a["z"] == axes_b["z"]:
        raise ValueError("expected only z axis change from Y2 to Z2")
    resolved_diffs = diff_paths(y2["resolved_config"], z2["resolved_config"])
    allowed = (
        "derived.mesh_cells", "derived.native_capacity_profile", "discretization.mesh_axis_cell_counts",
        "discretization.mesh_axis_z_values", "discretization.mesh_plan_id", "discretization.mesh_plan_sha256",
        "provenance.expected_output_parent", "provenance.input_sha256", "provenance.physical_model_sha256",
        "provenance.source_path", "run_id", "solver.native_capacity_profile",
    )
    allowed_prefixes = tuple(f"{q}{suffix}" for q in allowed for suffix in (".", "["))
    unexpected = [p for p in resolved_diffs if p not in allowed and not p.startswith(allowed_prefixes)]
    if unexpected:
        raise ValueError(f"unexpected resolved-config differences: {unexpected}")
    modal_comparison = amplitude_comparison(y2["mode_rows"], z2["mode_rows"])
    samples_a, samples_b = load_samples(y2), load_samples(z2)
    for axis in ("x_nm", "y_nm", "z_nm"):
        if not np.array_equal(samples_a[axis], samples_b[axis]):
            raise ValueError(f"common sample coordinate differs: {axis}")
    sample_metrics: dict[str, Any] = {}
    for field in SAMPLE_FIELDS:
        a, b = samples_a[field], samples_b[field]
        item = {"shape": list(a.shape), "dtype": str(a.dtype), **norm_metrics(a, b)}
        item["relative_l2_gate_1e-4_pass_on_saved_samples"] = bool(item["relative_l2_to_Y2"] <= 1e-4) if item["relative_l2_to_Y2"] is not None else None
        if a.ndim and a.shape[-1] == 3:
            item["per_component"] = [{"component": c, **norm_metrics(a[..., i], b[..., i])} for i, c in enumerate(("x", "y", "z"))]
        sample_metrics[field] = item
    totals = {}
    for field in y2["totals"]:
        a, b = y2["totals"][field], z2["totals"][field]
        delta = float(b - a)
        totals[field] = {"Y2": a, "Z2": b, "delta_Z2_minus_Y2": delta, "absolute_delta": abs(delta),
                         "gate_1e-5_pass": bool(abs(delta) <= 1e-5) if field in {"R_total", "T_total", "A_balance", "A_volume"} else None}
    fields = ["auxiliary_index", "side", "direction", "m", "n", "polarization", "propagating", "power_carrying",
              "beta_re", "beta_im", "boundary_phase_re", "boundary_phase_im"]
    for label in ("Y2", "Z2"):
        for prefix in ("raw_outgoing", "boundary_outgoing", "auxiliary_total_projection"):
            fields += [f"{label}_{prefix}_re", f"{label}_{prefix}_im"]
        fields += [f"{label}_R", f"{label}_T", f"{label}_modal_power_code_units", f"{label}_power_ratio"]
    fields += ["delta_boundary_outgoing_abs", "delta_R", "delta_T", "delta_modal_power_code_units"]
    OUT.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); w.writeheader()
        for a, b in zip(y2["mode_rows"], z2["mode_rows"], strict=True):
            row = {"auxiliary_index": int(a["auxiliary_index"]), "side": a["side"], "direction": a["direction"],
                   "m": int(a["m"]), "n": int(a["n"]), "polarization": a["polarization"],
                   "propagating": bool(a["propagating"]), "power_carrying": bool(a["power_carrying"]),
                   "beta_re": complex_value(a["beta"]).real, "beta_im": complex_value(a["beta"]).imag,
                   "boundary_phase_re": complex_value(a["boundary_phase"]).real, "boundary_phase_im": complex_value(a["boundary_phase"]).imag}
            for label, mode_row, case in (("Y2", a, y2), ("Z2", b, z2)):
                ai = int(mode_row["auxiliary_index"]); aux = case["aux_rows"][ai]
                for prefix, value in (("raw_outgoing", mode_row["outgoing_amplitude"]),
                                      ("boundary_outgoing", mode_row["outgoing_amplitude_at_boundary"]),
                                      ("auxiliary_total_projection", aux["auxiliary_amplitude_total_projection"])):
                    v = complex_value(value); row[f"{label}_{prefix}_re"], row[f"{label}_{prefix}_im"] = v.real, v.imag
                for field in ("R", "T", "modal_power_code_units", "power_ratio"): row[f"{label}_{field}"] = float(mode_row[field])
            db = complex_value(b["outgoing_amplitude_at_boundary"]) - complex_value(a["outgoing_amplitude_at_boundary"])
            row["delta_boundary_outgoing_abs"] = abs(db)
            row["delta_R"] = float(b["R"]) - float(a["R"]); row["delta_T"] = float(b["T"]) - float(a["T"])
            row["delta_modal_power_code_units"] = float(b["modal_power_code_units"]) - float(a["modal_power_code_units"])
            w.writerow(row)
    csv_sha = sha(CSV_OUT.read_bytes())
    report = {
        "schema": "task40.d13.same_relative_only_y2_z2_saved_output_comparison.v1",
        "scope": "offline comparison of finished Y2 and Z2 same-relative-only runs; no FE/factor/VTU/resource-stream reads",
        "identity": {label: {"source_sha": c["source_sha"], "input_sha256": c["input_sha256"],
            "physical_model_sha256": c["physical_model_sha256"], "resolved_config_sha256": c["resolved_config_sha256"],
            "resolved_diff_paths_Y2_to_Z2": resolved_diffs, "axis_cell_counts": c["axes"], "actual_cells": c["actual_cells"],
            "axis_sha256_le_f64": c["axis_sha256_le_f64"], "mode_count": c["mode_count"], "mode_sha256": c["mode_sha256"],
            "cutoff_policy": c["cutoff_policy"], "cutoff_relative_tolerance": c["cutoff_relative_tolerance"],
            "cutoff_identity_sha256": c["cutoff_identity_sha256"], "surface_q": c["surface_q"],
            "volume_quadrature_records": c["volume_q_records"], "qualification_status": c["qualification_status"],
            "full_dtn_status": c["full_dtn_status"], "run_summary_sha256": c["run_summary_sha256"],
            "workflow_phase_sha256": c["phase_sha256"], "direct_summary_sha256": c["direct_summary_sha256"],
            "sample_artifact_hashes": c["sample_artifacts"], "sample_metadata": c["sample_meta"]} for label, c in (("Y2", y2), ("Z2", z2))},
        "same_operator_checks": {"x_axis_exactly_equal": True, "y_axis_exactly_equal": True, "z_axis_changed_only": True,
            "mode_keys_order_branch_beta_boundary_phase_exact": True, "mode_sha_equal": True,
            "cutoff_identity_equal": True, "surface_q_equal": True, "volume_q_records_equal": True,
            "resolved_differences_within_mesh_and_provenance_paths": not unexpected,
            "source_sha_equal": y2["source_sha"] == z2["source_sha"],
            "interpretation": "The source commit changed to add the Z2 mesh plan/profile; this is not a source-SHA-equal pair. Resolved differences are limited to the Z axis/mesh-plan/profile/run provenance paths listed above; the mode inventory, sparse policy, quadrature, and reported material/incident identities match.",
            "operator_scope": "finite R13 active rectangle only; no full-DtN claim"},
        "global_observable_differences": totals,
        "modal_comparison": modal_comparison,
        "same_coordinate_saved_field_comparison": sample_metrics,
        "sample_coordinates": {a: {"shape": list(samples_a[a].shape), "dtype": str(samples_a[a].dtype), "sha256": array_sha(samples_a[a])} for a in ("x_nm", "y_nm", "z_nm")},
        "resource_and_solver": {label: {"resource": c["resource"], "solver": {k: c["solver"].get(k) for k in ("condensed_direct_relative", "condensed_direct_residual_gate", "original_A6_active_rectangle_relative", "original_A6_active_rectangle_relative_gate", "same_factor_correction_count")},
                "matrix": {"nz_used": c["matrix_info"].get("nz_used"), "nz_allocated": c["matrix_info"].get("nz_allocated"), "symbolic_calls": c["factor"].get("symbolic_calls"), "numeric_calls": c["factor"].get("numeric_calls"), "solve_calls": c["factor"].get("solve_calls")}}
            for label, c in (("Y2", y2), ("Z2", z2))},
        "limits": ["This is a two-level z-direction sensitivity comparison, not proof of continuum/z convergence.",
            "The sample arrays are finite common sample points, not a full-domain L2 norm.",
            "H_t_interface samples are horizontal z-plane samples, not canonical pillar-sidewall traces; sidewall gate remains NOT_MEASURED.",
            "Both solves remain AUTHORITY_LIMITED and FULL_DTN_NOT_VERIFIED; no omitted DtN channel was solved.",
            "Per-mode formal Task40 R/T threshold is applied to every propagating mode; all-612 and power-carrying nonpropagating modes are also retained as diagnostics."],
        "csv": {"path": str(CSV_OUT.relative_to(REPO)), "rows_excluding_header": 612,
            "sha256": csv_sha, "contains_all_mode_boundary/raw/aux amplitudes_and_R_T_power": True},
        "script": {"path": str(Path(__file__).resolve().relative_to(REPO)), "sha256": sha(Path(__file__).read_bytes())},
    }
    JSON_OUT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(JSON_OUT), "json_sha256": sha(JSON_OUT.read_bytes()), "csv": str(CSV_OUT), "csv_sha256": csv_sha,
                      "Y2": y2["actual_cells"], "Z2": z2["actual_cells"], "resolved_diff_paths": resolved_diffs}, sort_keys=True))


if __name__ == "__main__":
    main()
