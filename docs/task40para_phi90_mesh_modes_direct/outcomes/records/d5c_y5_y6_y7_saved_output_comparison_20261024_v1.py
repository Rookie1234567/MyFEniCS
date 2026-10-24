"""Offline D5C Y5/Y6/Y7 saved-output comparison; no FE, factor, VTU or resource-stream reads."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


W = Path("/home/fenics/Projects/Maxwell3D-Phi90")
ROOT = W / "results/si_block_phi90_50x50_17x20_h120"
OUT = W / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
RUNS = {
    "D5C-Y5": ROOT / "task40para_phi90_5_D5C_Y5_p6_direct_v1__full3d_direct__mpi1__Mna/20261023T140911.694951Z",
    "D5C-Y6": ROOT / "task40para_phi90_5_D5C_Y6_p6_direct_v1__full3d_direct__mpi1__Mna/20261024T021320.925991Z",
    "D5C-Y7": ROOT / "task40para_phi90_5_D5C_Y7_p6_direct_v1__full3d_direct__mpi1__Mna/20261024T061944.262318Z",
}
MODE_SHA = "752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc"
CUTOFF_ID = "d601c3aec1d625bef2b52031811b8dfa7cb2fed8fe7b2878959a75304945f5c9"
P_GLOBAL, P_MODE, P_FIELD = 1e-5, 1e-6, 1e-4
PAIRS = [("D5C-Y5", "D5C-Y6"), ("D5C-Y5", "D5C-Y7"), ("D5C-Y6", "D5C-Y7")]


def readj(path: Path):
    return json.loads(path.read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cval(value):
    return complex(float(value[0]), float(value[1]))


def norm(reference, candidate):
    a, b = np.asarray(reference), np.asarray(candidate)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError(f"invalid comparison arrays: {a.shape} vs {b.shape}")
    ref_norm = float(np.linalg.norm(a.ravel()))
    delta = b - a
    delta_norm = float(np.linalg.norm(delta.ravel()))
    return {
        "reference_l2": ref_norm,
        "difference_l2": delta_norm,
        "relative_l2_no_phase_fit": delta_norm / ref_norm if ref_norm else None,
        "max_abs_delta": float(np.max(np.abs(delta))),
        "max_abs_index": [int(i) for i in np.unravel_index(np.argmax(np.abs(delta)), a.shape)],
    }


def load_case(label: str, run: Path):
    manifest = readj(run / "run_manifest.json")
    summary = readj(run / "run_summary.json")
    phase = readj(run / "workflow_phase.json")
    direct = readj(run / "p6_condensed_direct_summary.json")
    resolved = readj(run / "resolved_config.json")
    power = readj(run / "numerical_output/dtn_port_power_metrics_3d.json")
    volume = readj(run / "numerical_output/volume_absorption.json")
    orders = readj(run / "numerical_output/dtn_port_diffraction_orders_3d.json")["orders"]
    evidence = readj(run / "numerical_output/task40_direct_factor_evidence/evidence.json")
    sample_meta = readj(run / "numerical_output/full3d_reference_samples.json")

    assert summary["status"] == "finished" and summary["exit_status"] == 0
    assert summary["resource_authority"]["descendants_cleared"] is True
    assert phase["phase"] == "complete" and phase["facts"]["passed"] is True
    assert direct["passed"] is True and direct["errors"] == []
    assert direct["mesh_evidence"]["status"] == "PASS"
    assert direct["mesh_evidence"]["actual_axes_match_frozen_d5c_coordinates"] is True
    assert power["active_mode_count"] == 3772 and power["active_mode_sha256"] == MODE_SHA
    assert len(orders) == 3772
    assert power["dtn_sparse_cutoff_policy"] == "scale_homogeneous_relative_only_v1"
    assert power["dtn_sparse_cutoff_identity_sha256"] == CUTOFF_ID
    op = evidence["operator_identity"]
    assert op["active_mode_count"] == 3772 and op["active_mode_sha256"] == MODE_SHA
    assert op["parent_mode_count"] == 3772 and op["parent_mode_sha256"] == MODE_SHA
    assert op["parent_quadrature_degree"] == 39
    assert op["dtn_sparse_cutoff_policy"] == "scale_homogeneous_relative_only_v1"
    assert op["dtn_sparse_cutoff_identity_sha256"] == CUTOFF_ID
    assert op["functional_store"] is False
    volume_records = op["volume_quadrature_records"]
    assert volume_records and all(
        x["quadrature_degree"] == 15 and x["quadrature_rule"] == "default"
        for x in volume_records
    )
    keyed = {
        (str(x["side"]), int(x["m"]), int(x["n"]), str(x["polarization"])): x
        for x in orders
    }
    assert len(keyed) == 3772

    archive = run / "numerical_output/full3d_reference_samples.npz"
    with np.load(archive, allow_pickle=False) as data:
        samples = {name: data[name].copy() for name in data.files}
    assert sample_meta["archive_sha256"] == sha(archive)
    physical = {k: resolved[k] for k in ("geometry", "materials", "incidence", "boundary")}
    return {
        "label": label,
        "run": run,
        "manifest": manifest,
        "summary": summary,
        "phase": phase,
        "direct": direct,
        "resolved": resolved,
        "power": power,
        "volume": volume,
        "keyed": keyed,
        "samples": samples,
        "sample_meta": sample_meta,
        "physical": physical,
        "evidence": evidence,
        "identity": {
            "run_id": manifest["run_id"],
            "source_sha": manifest["source_sha"],
            "input_sha256": manifest["input_sha256"],
            "physical_model_sha256": manifest["physical_model_sha256"],
            "resolved_config_sha256": manifest["resolved_config_sha256"],
            "run_manifest_sha256": sha(run / "run_manifest.json"),
            "run_summary_sha256": sha(run / "run_summary.json"),
            "direct_summary_sha256": sha(run / "p6_condensed_direct_summary.json"),
            "factor_evidence_sha256": sha(run / "numerical_output/task40_direct_factor_evidence/evidence.json"),
            "sample_archive_sha256": sha(archive),
            "sample_archive_internal_sha256": sample_meta["archive_sha256"],
            "mode_count": 3772,
            "mode_sha256": MODE_SHA,
            "surface_q": 39,
            "volume_q": 15,
            "volume_rule": "default",
            "cutoff_policy": op["dtn_sparse_cutoff_policy"],
            "cutoff_identity_sha256": CUTOFF_ID,
            "operator_scope": op["operator_scope"],
            "axis_cell_counts": resolved["discretization"]["mesh_axis_cell_counts"],
            "axis_sha256_le_f64": direct["mesh_evidence"]["axis_sha256_le_f64"],
            "actual_mesh_evidence": direct["mesh_evidence"],
            "field_sample_metadata": sample_meta,
            "single_run_passed": direct["passed"],
            "single_run_status": phase["facts"]["status"],
            "residuals": direct["residuals"],
            "full_dtn_status": op["full_dtn_status"],
        },
    }


def compare(reference, candidate):
    if reference["physical"] != candidate["physical"]:
        raise ValueError("geometry/material/incidence/boundary mismatch")
    if set(reference["keyed"]) != set(candidate["keyed"]):
        raise ValueError("modal key mismatch")
    keys = sorted(reference["keyed"])
    a, b = reference["keyed"], candidate["keyed"]
    for key in keys:
        for flag in ("propagating", "power_carrying", "rayleigh_warning"):
            if bool(a[key].get(flag)) != bool(b[key].get(flag)):
                raise ValueError(f"mode classification mismatch {key}: {flag}")
    groups = {
        "all_3772": keys,
        "power_carrying": [k for k in keys if a[k]["power_carrying"]],
        "propagating": [k for k in keys if a[k]["propagating"]],
    }
    per_mode = {}
    for group_name, group_keys in groups.items():
        per_mode[group_name] = {}
        for component in ("R", "T"):
            deltas = np.array([float(b[k][component]) - float(a[k][component]) for k in group_keys])
            i = int(np.argmax(np.abs(deltas))) if len(deltas) else 0
            per_mode[group_name][component] = {
                "count": len(group_keys),
                "max_abs_delta": float(abs(deltas[i])) if len(deltas) else 0.0,
                "signed_delta": float(deltas[i]) if len(deltas) else 0.0,
                "key": list(group_keys[i]) if len(deltas) else None,
                "reference": float(a[group_keys[i]][component]) if len(deltas) else None,
                "candidate": float(b[group_keys[i]][component]) if len(deltas) else None,
                "l2_delta": float(np.linalg.norm(deltas)),
                "over_limit_count": int(np.count_nonzero(np.abs(deltas) > P_MODE)),
                "limit": P_MODE,
                "pass": bool(not np.any(np.abs(deltas) > P_MODE)),
            }

    global_pairs = [
        ("R_total", reference["power"]["R_total"], candidate["power"]["R_total"], P_GLOBAL),
        ("T_total", reference["power"]["T_total"], candidate["power"]["T_total"], P_GLOBAL),
        ("A_balance", reference["power"]["A_balance"], candidate["power"]["A_balance"], P_GLOBAL),
        ("A_volume", reference["volume"]["A_volume_total"], candidate["volume"]["A_volume_total"], P_GLOBAL),
        ("R00_s", reference["power"]["R00_s"], candidate["power"]["R00_s"], P_MODE),
        ("R00_total", reference["power"]["R00_total"], candidate["power"]["R00_total"], P_MODE),
    ]
    global_observables = {}
    for name, ref, cand, limit in global_pairs:
        delta = float(cand) - float(ref)
        global_observables[name] = {
            "reference": float(ref),
            "candidate": float(cand),
            "signed_delta": delta,
            "abs_delta": abs(delta),
            "limit": limit,
            "pass": abs(delta) <= limit,
        }

    boundary_a = np.array([cval(a[k]["outgoing_amplitude_at_boundary"]) for k in keys])
    boundary_b = np.array([cval(b[k]["outgoing_amplitude_at_boundary"]) for k in keys])
    boundary = norm(boundary_a, boundary_b)
    bi = int(np.argmax(np.abs(boundary_b - boundary_a)))
    boundary.update({
        "count": len(keys),
        "max_delta_key": list(keys[bi]),
        "limit": P_FIELD,
        "pass": boundary["relative_l2_no_phase_fit"] is not None
        and boundary["relative_l2_no_phase_fit"] <= P_FIELD,
    })

    sa, sb = reference["samples"], candidate["samples"]
    coordinate_match = {k: bool(np.array_equal(sa[k], sb[k])) for k in ("x_nm", "y_nm", "z_nm", "interface_z_nm")}
    if not all(coordinate_match.values()):
        raise ValueError(f"sample coordinates differ: {coordinate_match}")
    fields = {}
    for name in ("E_V_per_m", "H_A_per_m"):
        fields[name] = norm(sa[name], sb[name])
        fields[name]["limit"] = P_FIELD
        fields[name]["pass"] = fields[name]["relative_l2_no_phase_fit"] is not None and fields[name]["relative_l2_no_phase_fit"] <= P_FIELD
    horizontal = {}
    for name in ("E_t_interface_V_per_m", "H_t_interface_A_per_m"):
        horizontal[name] = norm(sa[name], sb[name])
        horizontal[name]["scope"] = "horizontal sampled planes only; not canonical grating sidewalls"

    global_pass = all(global_observables[k]["pass"] for k in ("R_total", "T_total", "A_balance", "A_volume"))
    modes_pass = (
        all(per_mode["all_3772"][k]["pass"] and per_mode["power_carrying"][k]["pass"] for k in ("R", "T"))
        and global_observables["R00_s"]["pass"]
        and global_observables["R00_total"]["pass"]
    )
    fields_pass = boundary["pass"] and fields["E_V_per_m"]["pass"] and fields["H_A_per_m"]["pass"]
    return {
        "reference": reference["label"],
        "candidate": candidate["label"],
        "global_observables": global_observables,
        "per_mode_R_T": per_mode,
        "boundary_complex_amplitude": boundary,
        "same_coordinate_fields": {
            "coordinates_exact_equal": coordinate_match,
            "sample_coordinates_nm": {k: sa[k].tolist() for k in ("x_nm", "y_nm", "z_nm", "interface_z_nm")},
            "E_H": fields,
            "horizontal_Et_Ht_diagnostics_only": horizontal,
            "comparison": "saved complex arrays on exact common coordinates; no interpolation and no phase fitting",
            "canonical_sidewall": "NOT_MEASURED",
        },
        "gate_groups": {
            "global_R_T_A_balance_A_volume": global_pass,
            "all_3772_and_power_carrying_mode_R_T_including_R00_s": modes_pass,
            "boundary_and_same_coordinate_E_H": fields_pass,
        },
        "all_three_gate_groups_pass": bool(global_pass and modes_pass and fields_pass),
    }


def write_mode_csv(cases, pairs, path):
    fields = [
        "reference", "candidate", "side", "m", "n", "polarization", "propagating", "power_carrying",
        "R_reference", "R_candidate", "delta_R", "T_reference", "T_candidate", "delta_T",
        "boundary_reference_re", "boundary_reference_im", "boundary_candidate_re", "boundary_candidate_im",
        "boundary_delta_re", "boundary_delta_im", "boundary_delta_abs",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for ref_name, cand_name in pairs:
            a, b = cases[ref_name]["keyed"], cases[cand_name]["keyed"]
            for key in sorted(a):
                ar = cval(a[key]["outgoing_amplitude_at_boundary"])
                br = cval(b[key]["outgoing_amplitude_at_boundary"])
                writer.writerow({
                    "reference": ref_name,
                    "candidate": cand_name,
                    "side": key[0], "m": key[1], "n": key[2], "polarization": key[3],
                    "propagating": bool(a[key]["propagating"]),
                    "power_carrying": bool(a[key]["power_carrying"]),
                    "R_reference": a[key]["R"], "R_candidate": b[key]["R"], "delta_R": float(b[key]["R"]) - float(a[key]["R"]),
                    "T_reference": a[key]["T"], "T_candidate": b[key]["T"], "delta_T": float(b[key]["T"]) - float(a[key]["T"]),
                    "boundary_reference_re": ar.real, "boundary_reference_im": ar.imag,
                    "boundary_candidate_re": br.real, "boundary_candidate_im": br.imag,
                    "boundary_delta_re": (br - ar).real, "boundary_delta_im": (br - ar).imag,
                    "boundary_delta_abs": abs(br - ar),
                })


def main():
    cases = {label: load_case(label, path) for label, path in RUNS.items()}
    baseline_physical = cases["D5C-Y5"]["physical"]
    baseline_op = cases["D5C-Y5"]["evidence"]["operator_identity"]
    for label, case in cases.items():
        if case["physical"] != baseline_physical:
            raise ValueError(f"physical mismatch for {label}")
        op = case["evidence"]["operator_identity"]
        for key in (
            "active_mode_sha256", "active_mode_count", "degree", "dtn_sparse_cutoff_policy",
            "dtn_sparse_cutoff_relative_tolerance", "dtn_sparse_cutoff_identity_sha256",
            "parent_quadrature_degree", "volume_quadrature_records", "functional_store",
        ):
            if op[key] != baseline_op[key]:
                raise ValueError(f"operator identity mismatch for {label}: {key}")
    # Source transition Y5->Y6/Y7 changed only Task40 plan/profile/admission/tests, not numerical kernels.
    changed_src = subprocess.run(
        ["git", "diff", "--name-only", "70a64b0e133318d59b489b5475a9c346e8b5d3df..1207cb78889fba6de4fd03ea72a238b334aa61a7", "--", "src"],
        cwd=W, check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    numeric_kernel_paths = {
        "src/runners/p6_condensed_direct.py",
        "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
        "src/solvers/dtn_port_3d.py",
        "src/solvers/dtn_sparse_policy.py",
        "src/solvers/fullspace_partial_assembly.py",
    }
    if numeric_kernel_paths.intersection(changed_src):
        raise ValueError(f"numerical kernel changed across Y5/Y6 source revisions: {numeric_kernel_paths.intersection(changed_src)}")

    comparisons = [compare(cases[a], cases[b]) for a, b in PAIRS]
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "d5c_y5_y6_y7_all_3772_modes_20261024_v1.csv"
    write_mode_csv(cases, PAIRS, csv_path)
    payload = {
        "schema": "task40.d5c.y5_y6_y7_saved_output_comparison.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": "offline comparison of existing compact saved outputs only; no FE, factor, VTU, or resource-stream reads",
        "source_transition": {
            "Y5_source": cases["D5C-Y5"]["identity"]["source_sha"],
            "Y6_Y7_source": cases["D5C-Y6"]["identity"]["source_sha"],
            "changed_src_paths": changed_src,
            "numerical_kernel_paths_unchanged": sorted(numeric_kernel_paths),
            "note": "Y5 predates the D5C Y6/Y7 profile addition; physical configuration and live operator identities are checked equal here. The changed source paths are plan/profile/admission/test routing, not the listed numerical assembly/solver kernels.",
        },
        "identities": {name: case["identity"] for name, case in cases.items()},
        "thresholds": {
            "global_R_T_A_balance_A_volume_abs": P_GLOBAL,
            "each_channel_R_T_abs_all_3772_and_power_carrying": P_MODE,
            "R00_s_R00_total_abs": P_MODE,
            "boundary_complex_amplitude_relative_l2_no_phase_fit": P_FIELD,
            "same_coordinate_complex_E_H_relative_l2_no_phase_fit": P_FIELD,
        },
        "method": "Exact joins by (side,m,n,polarization); all 3772, power-carrying and propagating groups reported. The all-mode and power-carrying groups gate; propagating is an additional diagnostic only. Boundary uses outgoing amplitude at the boundary plane. Complex E/H are compared on exactly common saved coordinates with no interpolation and no phase fit.",
        "grid_scope": {
            "D5C-Y5": {"y_segments": [10, 6, 10], "y_cells": 26, "axis_counts": [6, 26, 6]},
            "D5C-Y6": {"y_segments": [12, 6, 12], "y_cells": 30, "axis_counts": [6, 30, 6]},
            "D5C-Y7": {"y_segments": [10, 10, 10], "y_cells": 30, "axis_counts": [6, 30, 6]},
            "comparisons": {
                "D5C-Y5_to_Y6": "y changes 10/6/10 to 12/6/12; x/z fixed to B",
                "D5C-Y5_to_Y7": "y changes 10/6/10 to 10/10/10; x/z fixed to B",
                "D5C-Y6_to_Y7": "same 30 y cells, allocation changes 12/6/12 to 10/10/10; each is independently derived from B; x/z fixed to B",
            },
        },
        "limitations": ["AUTHORITY_LIMITED", "FULL_DTN_NOT_VERIFIED", "canonical_sidewall_NOT_MEASURED", "horizontal Et/Ht are diagnostics only"],
        "mode_csv": {"path": str(csv_path), "sha256": sha(csv_path), "bytes": csv_path.stat().st_size, "rows_expected": 3772 * len(PAIRS)},
        "comparison_script_sha256": sha(Path(__file__)),
        "comparisons": comparisons,
    }
    json_path = OUT / "d5c_y5_y6_y7_saved_output_comparison_20261024_v1.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "json": str(json_path), "json_sha256": sha(json_path),
        "csv": str(csv_path), "csv_sha256": sha(csv_path), "csv_bytes": csv_path.stat().st_size,
        "comparison_script_sha256": sha(Path(__file__)),
        "pairs": [{
            "reference": x["reference"], "candidate": x["candidate"],
            "global_pass": x["gate_groups"]["global_R_T_A_balance_A_volume"],
            "mode_pass": x["gate_groups"]["all_3772_and_power_carrying_mode_R_T_including_R00_s"],
            "field_pass": x["gate_groups"]["boundary_and_same_coordinate_E_H"],
            "all_three_pass": x["all_three_gate_groups_pass"],
            "global_abs_deltas": {k: v["abs_delta"] for k, v in x["global_observables"].items()},
            "all_mode_max_R_T": {k: x["per_mode_R_T"]["all_3772"][k] for k in ("R", "T")},
            "power_carrying_max_R_T": {k: x["per_mode_R_T"]["power_carrying"][k] for k in ("R", "T")},
            "propagating_max_R_T_diagnostic": {k: x["per_mode_R_T"]["propagating"][k] for k in ("R", "T")},
            "boundary_rel": x["boundary_complex_amplitude"]["relative_l2_no_phase_fit"],
            "field_rel": {k: x["same_coordinate_fields"]["E_H"][k]["relative_l2_no_phase_fit"] for k in ("E_V_per_m", "H_A_per_m")},
            "horizontal_Et_Ht_diagnostic_rel": {k: x["same_coordinate_fields"]["horizontal_Et_Ht_diagnostics_only"][k]["relative_l2_no_phase_fit"] for k in ("E_t_interface_V_per_m", "H_t_interface_A_per_m")},
        } for x in comparisons],
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
