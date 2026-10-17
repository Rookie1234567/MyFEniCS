#!/usr/bin/env python3
"""Offline comparison of the authorized H15-YZ480 field with existing anchors.

Reads compact run metadata/output JSON and the four saved reference-sample NPZs.
It does not read VTU or resource streams, build a mesh, assemble, factor, or solve.
All complex field and modal comparisons are direct, with no phase fitting.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
MODEL = "si_block_phi90_50x50_17x20_h120"
RESULTS = ROOT / "results" / MODEL
RECORDS = ROOT / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
CASES = {
    "H15_YZ480": RESULTS
    / "task40_phi90_13p5_H15_YZ480_p6_direct_v1__full3d_direct__mpi1__Mna/20261017T095134.921987Z",
    "H15_Y": RESULTS
    / "task40_phi90_13p5_H15_Y_p6_direct_v1__full3d_direct__mpi1__Mna/20261017T055854.344877Z",
    "D13_Y2_relative_only": RESULTS
    / "task40_phi90_13p5_D13_Y2_p6_direct_v1__full3d_direct__mpi1__Mna/20261016T190312.893443Z",
    "D13_Y3_relative_only": RESULTS
    / "task40_phi90_13p5_D13_Y3_p6_direct_v1__full3d_direct__mpi1__Mna/20261016T202834.284773Z",
}
MODE_SHA = "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
POWER_TOL = 1e-6
GLOBAL_POWER_TOL = 1e-5
FIELD_REL_TOL = 1e-4
MODE_AMPLITUDE_REL_TOL = 1e-4


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _mode_key(row: dict[str, Any]) -> tuple[str, int, int, str]:
    return (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"]))


def _complex(value: list[float]) -> complex:
    result = complex(float(value[0]), float(value[1]))
    if not (math.isfinite(result.real) and math.isfinite(result.imag)):
        raise ValueError("non-finite modal complex value")
    return result


def _norm(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    a = np.asarray(reference)
    b = np.asarray(candidate)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError(f"invalid or mismatched arrays: {a.shape} vs {b.shape}")
    delta = b - a
    a_l2 = float(np.linalg.norm(a.ravel()))
    delta_l2 = float(np.linalg.norm(delta.ravel()))
    index = tuple(int(i) for i in np.unravel_index(int(np.argmax(np.abs(delta))), delta.shape))
    return {
        "reference_l2": a_l2,
        "difference_l2": delta_l2,
        "relative_l2_to_reference": delta_l2 / a_l2 if a_l2 else None,
        "max_abs_difference": float(np.max(np.abs(delta))),
        "max_abs_index": list(index),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_case(label: str, run: Path) -> dict[str, Any]:
    manifest = _read_json(run / "run_manifest.json")
    summary = _read_json(run / "run_summary.json")
    phase = _read_json(run / "workflow_phase.json")
    direct_summary = _read_json(run / "p6_condensed_direct_summary.json")
    out = run / "numerical_output"
    orders_doc = _read_json(out / "dtn_port_diffraction_orders_3d.json")
    power = _read_json(out / "dtn_port_power_metrics_3d.json")
    volume = _read_json(out / "volume_absorption.json")
    sample_meta = _read_json(out / "full3d_reference_samples.json")
    evidence_path = out / "task40_direct_factor_evidence" / "evidence.json"
    evidence_bytes = evidence_path.read_bytes()
    evidence = json.loads(evidence_bytes)
    if summary.get("status") != "finished" or summary.get("exit_status") != 0:
        raise ValueError(f"{label}: run did not naturally finish with exit 0")
    if phase.get("phase") != "complete" or phase.get("facts", {}).get("passed") is not True:
        raise ValueError(f"{label}: direct solver checks did not pass")
    if direct_summary.get("passed") is not True or direct_summary.get("authority") != "AUTHORITY_LIMITED":
        raise ValueError(f"{label}: unexpected direct summary status/authority")
    if power.get("active_mode_count") != 612 or power.get("active_mode_sha256") != MODE_SHA:
        raise ValueError(f"{label}: active mode identity mismatch")
    if power.get("dtn_sparse_cutoff_policy") != "scale_homogeneous_relative_only_v1":
        raise ValueError(f"{label}: not the same relative-only cutoff policy")
    operator = evidence.get("operator_identity", {})
    if operator.get("active_mode_count") != 612 or operator.get("active_mode_sha256") != MODE_SHA:
        raise ValueError(f"{label}: direct-factor evidence mode identity mismatch")
    if operator.get("dtn_sparse_cutoff_policy") != "scale_homogeneous_relative_only_v1":
        raise ValueError(f"{label}: factor evidence is not relative-only")
    if operator.get("parent_quadrature_degree") != 28:
        raise ValueError(f"{label}: frozen surface quadrature is not q28")
    if any(
        record.get("quadrature_degree") != 15
        for record in operator.get("volume_quadrature_records", [])
    ):
        raise ValueError(f"{label}: frozen volume quadrature is not q15/default")
    orders = orders_doc["orders"]
    keyed = {_mode_key(row): row for row in orders}
    if len(orders) != 612 or len(keyed) != 612:
        raise ValueError(f"{label}: expected exactly 612 unique signed modes")
    physical = {
        key: manifest.get("resolved_config", {}).get(key)
        for key in ("geometry", "materials", "incidence", "boundary")
    }
    resolved = _read_json(run / "resolved_config.json")
    physical = {key: resolved.get(key) for key in ("geometry", "materials", "incidence", "boundary")}
    sample_archive = out / sample_meta["archive"]
    with np.load(sample_archive, allow_pickle=False) as archive:
        samples = {name: archive[name].copy() for name in archive.files}
    return {
        "label": label,
        "run": run,
        "manifest": manifest,
        "summary": summary,
        "phase": phase,
        "direct_summary": direct_summary,
        "resolved": resolved,
        "physical": physical,
        "orders": orders,
        "keyed": keyed,
        "power": power,
        "volume": volume,
        "evidence": evidence,
        "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        "sample_meta": sample_meta,
        "sample_archive_sha256_actual": _sha256(sample_archive),
        "samples": samples,
    }


def _compare_modes(reference: dict[str, Any], candidate: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    left = reference["keyed"]
    right = candidate["keyed"]
    if set(left) != set(right):
        raise ValueError(f"{reference['label']} and {candidate['label']} signed keys differ")
    keys = sorted(left)
    for flag in ("propagating", "power_carrying", "rayleigh_warning"):
        mismatch = sum(bool(left[k].get(flag)) != bool(right[k].get(flag)) for k in keys)
        if mismatch:
            raise ValueError(f"{flag} differs for {mismatch} modes in {candidate['label']}")
    groups = {
        "all_612": keys,
        "propagating": [k for k in keys if left[k]["propagating"]],
        "power_carrying": [k for k in keys if left[k]["power_carrying"]],
        "evanescent": [k for k in keys if not left[k]["propagating"]],
        "non_power_carrying": [k for k in keys if not left[k]["power_carrying"]],
    }
    groups_out: dict[str, Any] = {}
    for name, members in groups.items():
        base_boundary = np.array([_complex(left[k]["outgoing_amplitude_at_boundary"]) for k in members])
        candidate_boundary = np.array([_complex(right[k]["outgoing_amplitude_at_boundary"]) for k in members])
        base_raw = np.array([_complex(left[k]["outgoing_amplitude"]) for k in members])
        candidate_raw = np.array([_complex(right[k]["outgoing_amplitude"]) for k in members])
        groups_out[name] = {
            "mode_count": len(members),
            "boundary_outgoing": _norm(base_boundary, candidate_boundary),
            "reference_plane_outgoing": _norm(base_raw, candidate_raw),
        }
    propagating = groups["propagating"]
    global_out: dict[str, Any] = {}
    for name in ("R_total", "R00_s", "R00_total", "T_total", "A_balance"):
        a = float(reference["power"][name]); b = float(candidate["power"][name]); delta = b - a
        tol = POWER_TOL if name == "R00_s" else GLOBAL_POWER_TOL
        global_out[name] = {"reference": a, "candidate": b, "delta": delta, "absolute_delta": abs(delta), "tolerance": tol, "status": "PASS" if abs(delta) <= tol else "FAIL"}
    a = float(reference["volume"]["A_volume_total"]); b = float(candidate["volume"]["A_volume_total"]); delta = b - a
    global_out["A_volume_total"] = {"reference": a, "candidate": b, "delta": delta, "absolute_delta": abs(delta), "tolerance": GLOBAL_POWER_TOL, "status": "PASS" if abs(delta) <= GLOBAL_POWER_TOL else "FAIL"}
    propagation: dict[str, Any] = {}
    for component in ("R", "T"):
        deltas = np.array([float(right[k][component]) - float(left[k][component]) for k in propagating])
        i = int(np.argmax(np.abs(deltas))) if deltas.size else 0
        key = propagating[i] if propagating else None
        maximum = float(abs(deltas[i])) if deltas.size else 0.0
        propagation[component] = {
            "mode_count": len(propagating),
            "max_abs_delta": maximum,
            "max_mode": {"side": key[0], "m": key[1], "n": key[2], "polarization": key[3]} if key else None,
            "count_abs_delta_over_tolerance": int(np.count_nonzero(np.abs(deltas) > POWER_TOL)),
            "tolerance": POWER_TOL,
            "status": "PASS" if maximum <= POWER_TOL else "FAIL",
        }
    all_mode_power: dict[str, Any] = {}
    for component in ("R", "T"):
        deltas = np.array([float(right[k][component]) - float(left[k][component]) for k in keys])
        all_mode_power[component] = {"l2_absolute": float(np.linalg.norm(deltas)), "max_absolute": float(np.max(np.abs(deltas))), "max_mode": {"side": keys[int(np.argmax(np.abs(deltas)))][0], "m": keys[int(np.argmax(np.abs(deltas)))][1], "n": keys[int(np.argmax(np.abs(deltas)))][2], "polarization": keys[int(np.argmax(np.abs(deltas)))][3]}}
    per_mode_power_scope: dict[str, Any] = {}
    for scope_name in ("all_612", "power_carrying", "propagating"):
        scope_keys = groups[scope_name]
        components: dict[str, Any] = {}
        for component in ("R", "T"):
            deltas = np.array([float(right[k][component]) - float(left[k][component]) for k in scope_keys])
            max_index = int(np.argmax(np.abs(deltas))) if deltas.size else 0
            max_key = scope_keys[max_index] if scope_keys else None
            max_delta = float(deltas[max_index]) if deltas.size else 0.0
            components[component] = {
                "max_abs_delta": abs(max_delta),
                "signed_delta": max_delta,
                "max_mode": {"side": max_key[0], "m": max_key[1], "n": max_key[2], "polarization": max_key[3]} if max_key else None,
                "count_abs_delta_over_tolerance": int(np.count_nonzero(np.abs(deltas) > POWER_TOL)),
                "tolerance": POWER_TOL,
                "status": "PASS" if abs(max_delta) <= POWER_TOL else "FAIL",
            }
        per_mode_power_scope[scope_name] = {"mode_count": len(scope_keys), "components": components}
    amplitude_gate = groups_out["all_612"]["boundary_outgoing"]
    amplitude_gate["tolerance"] = MODE_AMPLITUDE_REL_TOL
    amplitude_gate["status"] = "PASS" if amplitude_gate["relative_l2_to_reference"] is not None and amplitude_gate["relative_l2_to_reference"] <= MODE_AMPLITUDE_REL_TOL else "FAIL"
    rows = []
    for key in keys:
        a=left[key]; b=right[key]
        ab=_complex(a["outgoing_amplitude_at_boundary"]); bb=_complex(b["outgoing_amplitude_at_boundary"])
        ar=_complex(a["outgoing_amplitude"]); br=_complex(b["outgoing_amplitude"])
        rows.append({
            "reference":reference["label"],"candidate":candidate["label"],"side":key[0],"m":key[1],"n":key[2],"polarization":key[3],"propagating":bool(a["propagating"]),"power_carrying":bool(a["power_carrying"]),
            "reference_boundary_re":ab.real,"reference_boundary_im":ab.imag,"candidate_boundary_re":bb.real,"candidate_boundary_im":bb.imag,"boundary_delta_abs":abs(bb-ab),"boundary_delta_rel_to_reference":abs(bb-ab)/abs(ab) if abs(ab)>0 else None,
            "reference_raw_re":ar.real,"reference_raw_im":ar.imag,"candidate_raw_re":br.real,"candidate_raw_im":br.imag,"raw_delta_abs":abs(br-ar),
            "reference_R":float(a["R"]),"candidate_R":float(b["R"]),"delta_R":float(b["R"])-float(a["R"]),"reference_T":float(a["T"]),"candidate_T":float(b["T"]),"delta_T":float(b["T"])-float(a["T"]),
        })
    return ({"reference":reference["label"],"candidate":candidate["label"],"modal_classification_mismatch_counts":{"propagating":0,"power_carrying":0,"rayleigh_warning":0},"groups":groups_out,"all_612_boundary_amplitude_gate":amplitude_gate,"global_R_T_A":{"metrics":global_out,"per_propagating_mode_power":propagation,"per_mode_power_scope_metrics":per_mode_power_scope,"all_mode_power_deltas":all_mode_power}},rows)


def _compare_fields(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    a=reference["samples"]; b=candidate["samples"]
    coordinates={}
    for name in ("x_nm","y_nm","z_nm","interface_z_nm"):
        equal=bool(np.array_equal(a[name],b[name]))
        coords_a=np.ascontiguousarray(np.asarray(a[name],dtype="<f8")); coords_b=np.ascontiguousarray(np.asarray(b[name],dtype="<f8"))
        coordinates[name]={"exact_equal":equal,"reference_sha256_le_f64":hashlib.sha256(coords_a.tobytes()).hexdigest(),"candidate_sha256_le_f64":hashlib.sha256(coords_b.tobytes()).hexdigest(),"values":np.asarray(a[name]).astype(float).tolist()}
        if not equal: raise ValueError(f"saved sample coordinates differ: {reference['label']} vs {candidate['label']} ({name})")
    field_metrics={}
    for name in ("E_V_per_m","H_A_per_m"):
        metric=_norm(a[name],b[name]); metric["tolerance"] = FIELD_REL_TOL; metric["status"]="PASS" if metric["relative_l2_to_reference"] is not None and metric["relative_l2_to_reference"]<=FIELD_REL_TOL else "FAIL"
        metric["by_component"]={component:_norm(a[name][...,i],b[name][...,i]) for i,component in enumerate(("x","y","z"))}
        field_metrics[name]=metric
    tangential={}
    for name in ("E_t_interface_V_per_m","H_t_interface_A_per_m"):
        metric=_norm(a[name],b[name]); metric["tolerance"]=FIELD_REL_TOL; metric["status"]="PASS" if metric["relative_l2_to_reference"] is not None and metric["relative_l2_to_reference"]<=FIELD_REL_TOL else "FAIL"; metric["scope"]="horizontal z-plane tangential samples only; not canonical pillar sidewalls"
        tangential[name]=metric
    return {"comparison_method":"direct complex arrays at exactly matching saved coordinates; no interpolation or phase fit","coordinate_identity":coordinates,"array_shape_z_y_x_component":reference["sample_meta"].get("array_shape_z_y_x_component"),"point_count":reference["sample_meta"].get("point_count"),"reference_archive_sha256":reference["sample_meta"].get("archive_sha256"),"candidate_archive_sha256":candidate["sample_meta"].get("archive_sha256"),"E_H":field_metrics,"horizontal_tangential_traces":tangential,"canonical_pillar_sidewall_gate":"NOT_MEASURED"}


def main() -> None:
    cases={label:_load_case(label,path) for label,path in CASES.items()}
    candidate=cases["H15_YZ480"]
    for label,case in cases.items():
        if case["physical"]!=candidate["physical"]:
            raise ValueError(f"physical identity differs: {label}")
    comparisons={}; csv_rows=[]
    for label in ("H15_Y","D13_Y2_relative_only","D13_Y3_relative_only"):
        reference=cases[label]
        modal,rows=_compare_modes(reference,candidate); csv_rows.extend(rows)
        comparisons[label]={"modal":modal,"saved_fields":_compare_fields(reference,candidate),"scope":"saved-output comparison only; H15-YZ480 changes y and z relative to these anchors; cross-family comparisons are not single-axis convergence proof"}
    identity={}
    for label,case in cases.items():
        run=case["run"]; manifest=case["manifest"]; direct=case["direct_summary"]
        mesh=direct.get("mesh_evidence",{})
        operator=case["evidence"].get("operator_identity",{})
        identity[label]={
            "run_directory":str(run),"run_id":manifest.get("run_id"),"source_sha":manifest.get("source_sha"),"input_sha256":manifest.get("input_sha256"),"physical_model_sha256":manifest.get("physical_model_sha256"),"resolved_config_sha256":manifest.get("resolved_config_sha256"),
            "run_manifest_sha256":_sha256(run/"run_manifest.json"),"run_summary_sha256":_sha256(run/"run_summary.json"),"direct_summary_sha256":_sha256(run/"p6_condensed_direct_summary.json"),"direct_factor_evidence_sha256":case["evidence_sha256"],
            "exit_status":case["summary"].get("exit_status"),"result_classification":case["summary"].get("result_classification"),"solver_passed":case["phase"].get("facts",{}).get("passed"),"authority":direct.get("authority"),"full_dtn_status":case["power"].get("full_dtn_status"),
            "axis_cell_counts":mesh.get("axis_cell_counts"),"actual_global_cell_count":mesh.get("actual_global_cell_count"),"axis_sha256_le_f64":mesh.get("axis_sha256_le_f64"),"active_mode_count":case["power"].get("active_mode_count"),"active_mode_sha256":case["power"].get("active_mode_sha256"),
            "surface_quadrature_degree":operator.get("parent_quadrature_degree"),"volume_quadrature_records":operator.get("volume_quadrature_records"),"cutoff_policy":operator.get("dtn_sparse_cutoff_policy"),"cutoff_relative_tolerance":operator.get("dtn_sparse_cutoff_relative_tolerance"),"sample_archive_sha256":case["sample_meta"].get("archive_sha256"),"sample_archive_sha256_actual":case["sample_archive_sha256_actual"],
            "R_total":case["power"].get("R_total"),"R00_s":case["power"].get("R00_s"),"T_total":case["power"].get("T_total"),"A_balance":case["power"].get("A_balance"),"A_volume_total":case["volume"].get("A_volume_total"),
        }
    payload={
        "schema":"task40.h15_yz480_vs_h15_y_d13_y2_y3_saved_output_comparison.v1",
        "scope":"offline saved-output comparison only; no FE, factor, VTU, or resource-stream reads",
        "analysis_script":{"path":str(Path(__file__).relative_to(ROOT)),"sha256":_sha256(Path(__file__))},
        "candidate":"H15_YZ480 field14; x fixed to H15-Y, y and z both changed relative to H15-Y",
        "same_policy":"All four compared runs use 612 modes with the exact same SHA, q28 surface/q15 default volume, and scale_homogeneous_relative_only_v1 cutoff at 1e-13.",
        "comparison_method":"Exact signed modal keys and same saved sample coordinates; complex amplitudes and E/H are compared without phase fitting or interpolation.",
        "thresholds":{"global_R_T_A_balance_A_volume_absolute_difference":GLOBAL_POWER_TOL,"R00_s_absolute_difference":POWER_TOL,"per_mode_R_T_absolute_difference_all_612_power_carrying_and_propagating":POWER_TOL,"per_propagating_mode_R_T_absolute_difference":POWER_TOL,"all_612_boundary_outgoing_amplitude_relative_l2":MODE_AMPLITUDE_REL_TOL,"same_coordinate_complex_E_H_and_horizontal_tangential_relative_l2":FIELD_REL_TOL},
        "cases":identity,
        "comparisons":comparisons,
        "limitations":["H15-YZ480 changes y and z together relative to H15-Y; cross-family comparison with D13-Y2/Y3 also changes y and z, so differences cannot be assigned to one axis.","A run passing its own direct-solver gates does not imply cross-mesh output gates pass.","All runs are finite R13 and FULL_DTN_NOT_VERIFIED / AUTHORITY_LIMITED.","Saved E_t/H_t interface arrays are horizontal z-plane samples, not canonical pillar sidewall traces; sidewall gate remains NOT_MEASURED."]
    }
    out_json=RECORDS/"h15_yz480_vs_h15_y_d13_y2_y3_same_relative_only_v1.json"
    out_csv=RECORDS/"h15_yz480_vs_h15_y_d13_y2_y3_all_612_modes_v1.csv"
    out_json.write_text(json.dumps(payload,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    columns=list(csv_rows[0]) if csv_rows else []
    with out_csv.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=columns,lineterminator="\n");writer.writeheader();writer.writerows(csv_rows)
    print(json.dumps({"json":str(out_json),"csv":str(out_csv),"rows":len(csv_rows)},sort_keys=True))


if __name__ == "__main__":
    main()
