#!/usr/bin/env python3
"""Corrected offline H15-Y versus same-policy D13-Y2/Y3 comparison.

Reads small run identity/output JSON plus the saved reference-sample NPZs.
It does not read VTU/resources, build a mesh, assemble, factor, or solve.
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
H15_Y = RESULTS / (
    "task40_phi90_13p5_H15_Y_p6_direct_v1__full3d_direct__mpi1__Mna/"
    "20261017T055854.344877Z"
)
D13_CATALOG = RECORDS / "d13_y2_y3_same_relative_only_comparison_v1.json"
BASE_LABEL = "H15_Y"
CASE_LABELS = {
    "D13_Y2_relative_only": "Y2_relative_only",
    "D13_Y3_relative_only": "Y3_relative_only",
}
MODE_SHA = "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
POWER_TOL = 1e-6
GLOBAL_POWER_TOL = 1e-5
FIELD_REL_TOL = 1e-4
MODE_AMPLITUDE_REL_TOL = 1e-4


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _key(row: dict[str, Any]) -> tuple[str, int, int, str]:
    return (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"]))


def _complex(value: list[float]) -> complex:
    result = complex(float(value[0]), float(value[1]))
    if not (math.isfinite(result.real) and math.isfinite(result.imag)):
        raise ValueError("non-finite modal complex value")
    return result


def _canonical_hash(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values, dtype="<f8"))
    return hashlib.sha256(array.tobytes()).hexdigest()


def _norm(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    a = np.asarray(reference)
    b = np.asarray(candidate)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError(f"invalid or mismatched arrays: {a.shape} vs {b.shape}")
    delta = b - a
    a_l2 = float(np.linalg.norm(a.ravel()))
    delta_l2 = float(np.linalg.norm(delta.ravel()))
    idx = tuple(int(i) for i in np.unravel_index(int(np.argmax(np.abs(delta))), delta.shape))
    return {
        "reference_l2": a_l2,
        "difference_l2": delta_l2,
        "relative_l2_to_H15_Y": delta_l2 / a_l2 if a_l2 else None,
        "max_abs_difference": float(np.max(np.abs(delta))),
        "max_abs_index": list(idx),
    }


def _load_run(label: str, run: Path, catalog_case: dict[str, Any] | None) -> dict[str, Any]:
    manifest = _read_json(run / "run_manifest.json")
    phase = _read_json(run / "workflow_phase.json")
    summary = _read_json(run / "run_summary.json")
    if phase.get("phase") != "complete" or phase.get("facts", {}).get("passed") is not True:
        raise ValueError(f"{label} did not pass the workflow")
    if summary.get("status") != "finished" or summary.get("exit_status") != 0:
        raise ValueError(f"{label} did not naturally finish with exit 0")
    out = run / "numerical_output"
    modes_json = _read_json(out / "dtn_port_diffraction_orders_3d.json")
    power = _read_json(out / "dtn_port_power_metrics_3d.json")
    volume = _read_json(out / "volume_absorption.json")
    sample_meta = _read_json(out / "full3d_reference_samples.json")
    evidence_path = out / "task40_direct_factor_evidence" / "evidence.json"
    evidence_bytes = evidence_path.read_bytes()
    evidence = json.loads(evidence_bytes)
    evidence_identity = evidence.get("operator_identity", {})
    if evidence_identity.get("active_mode_count") != 612 or evidence_identity.get("active_mode_sha256") != MODE_SHA:
        raise ValueError(f"{label} direct-factor evidence mode identity mismatch")
    if evidence_identity.get("dtn_sparse_cutoff_policy") != "scale_homogeneous_relative_only_v1":
        raise ValueError(f"{label} direct-factor evidence is not relative-only")
    if catalog_case is not None:
        hashes = catalog_case.get("artifact_hashes", {})
        for artifact_name, artifact_path in (
            ("run_manifest_sha256", run / "run_manifest.json"),
            ("run_summary_sha256", run / "run_summary.json"),
        ):
            expected_hash = catalog_case.get(artifact_name) or hashes.get(artifact_name)
            if expected_hash:
                actual_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    raise ValueError(f"{label} {artifact_name} differs from catalog")
        expected_evidence_hash = catalog_case.get("direct_factor_evidence_sha256") or hashes.get("direct_factor_evidence_sha256")
        if expected_evidence_hash and hashlib.sha256(evidence_bytes).hexdigest() != expected_evidence_hash:
            raise ValueError(f"{label} direct-factor evidence hash differs from catalog")
    with np.load(out / "full3d_reference_samples.npz", allow_pickle=False) as archive:
        samples = {name: archive[name].copy() for name in archive.files}
    orders = modes_json["orders"]
    keyed = {_key(row): row for row in orders}
    if len(orders) != 612 or len(keyed) != 612:
        raise ValueError(f"{label} does not contain 612 unique modes")
    if power.get("active_mode_count") != 612 or power.get("active_mode_sha256") != MODE_SHA:
        raise ValueError(f"{label} mode identity mismatch")
    if catalog_case is not None:
        catalog_count = catalog_case.get("active_mode_count", catalog_case.get("mode_count"))
        catalog_sha = catalog_case.get("active_mode_sha256", catalog_case.get("mode_sha256"))
        if catalog_count != 612 or catalog_sha != MODE_SHA:
            raise ValueError(f"catalog mode identity mismatch for {label}")
        if catalog_case["run_directory"] != str(run):
            raise ValueError(f"catalog/run path mismatch for {label}")
        if catalog_case.get("surface_quadrature_degree") != 28:
            raise ValueError(f"{label} surface quadrature is not the frozen q28 contract")
        volume_records = catalog_case.get("volume_quadrature_records") or []
        if not volume_records or any(item.get("quadrature_degree") != 15 for item in volume_records):
            raise ValueError(f"{label} volume quadrature is not the frozen q15 contract")
    resolved = _read_json(run / "resolved_config.json")
    physical = {
        key: resolved[key]
        for key in ("geometry", "materials", "incidence", "boundary")
    }
    return {
        "label": label,
        "run": run,
        "manifest": manifest,
        "phase": phase,
        "summary": summary,
        "resolved": resolved,
        "physical_identity": physical,
        "catalog": catalog_case,
        "orders": orders,
        "keyed": keyed,
        "power": power,
        "volume": volume,
        "direct_factor_evidence": evidence,
        "direct_factor_evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        "sample_meta": sample_meta,
        "samples": samples,
    }


def _comparison(base: dict[str, Any], candidate: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    left = base["keyed"]
    right = candidate["keyed"]
    if set(left) != set(right):
        raise ValueError("modal keys differ")
    keys = sorted(left)
    class_mismatch = {
        name: sum(bool(left[key].get(name)) != bool(right[key].get(name)) for key in keys)
        for name in ("propagating", "power_carrying", "rayleigh_warning")
    }
    if any(class_mismatch.values()):
        raise ValueError(f"modal branch/classification mismatch: {class_mismatch}")
    groups = {
        "all_612": keys,
        "propagating": [key for key in keys if left[key]["propagating"]],
        "power_carrying": [key for key in keys if left[key]["power_carrying"]],
        "evanescent": [key for key in keys if not left[key]["propagating"]],
        "non_power_carrying": [key for key in keys if not left[key]["power_carrying"]],
    }
    group_metrics: dict[str, Any] = {}
    for name, members in groups.items():
        a = np.array([_complex(left[k]["outgoing_amplitude_at_boundary"]) for k in members])
        b = np.array([_complex(right[k]["outgoing_amplitude_at_boundary"]) for k in members])
        raw_a = np.array([_complex(left[k]["outgoing_amplitude"]) for k in members])
        raw_b = np.array([_complex(right[k]["outgoing_amplitude"]) for k in members])
        group_metrics[name] = {
            "boundary_outgoing": _norm(a, b),
            "raw_reference_plane_outgoing": _norm(raw_a, raw_b),
        }
    propagating = groups["propagating"]
    per_mode_deltas = {
        "R": np.array([float(right[k]["R"]) - float(left[k]["R"]) for k in keys]),
        "T": np.array([float(right[k]["T"]) - float(left[k]["T"]) for k in keys]),
    }
    per_propagating = {
        component: np.array([float(right[k][component]) - float(left[k][component]) for k in propagating])
        for component in ("R", "T")
    }
    global_fields = ("R_total", "R00_s", "R00_total", "T_total", "A_balance")
    base_power = base["power"]
    case_power = candidate["power"]
    global_delta = {
        name: {
            "H15_Y": float(base_power[name]),
            candidate["label"]: float(case_power[name]),
            "delta": float(case_power[name]) - float(base_power[name]),
            "absolute_delta": abs(float(case_power[name]) - float(base_power[name])),
            "task_tolerance": GLOBAL_POWER_TOL if name != "R00_s" else POWER_TOL,
            "status": "PASS" if abs(float(case_power[name]) - float(base_power[name])) <= (GLOBAL_POWER_TOL if name != "R00_s" else POWER_TOL) else "FAIL",
        }
        for name in global_fields
    }
    base_avol = float(base["volume"]["A_volume_total"])
    case_avol = float(candidate["volume"]["A_volume_total"])
    global_delta["A_volume_total"] = {
        "H15_Y": base_avol,
        candidate["label"]: case_avol,
        "delta": case_avol - base_avol,
        "absolute_delta": abs(case_avol - base_avol),
        "task_tolerance": GLOBAL_POWER_TOL,
        "status": "PASS" if abs(case_avol - base_avol) <= GLOBAL_POWER_TOL else "FAIL",
    }
    propagation_metrics = {}
    for component, delta in per_propagating.items():
        max_i = int(np.argmax(np.abs(delta))) if delta.size else 0
        max_key = propagating[max_i] if propagating else None
        propagation_metrics[component] = {
            "mode_count": int(delta.size),
            "max_abs_delta": float(abs(delta[max_i])) if delta.size else 0.0,
            "max_delta_key": {"side": max_key[0], "m": max_key[1], "n": max_key[2], "polarization": max_key[3]} if max_key else None,
            "count_abs_delta_over_1e-6": int(np.count_nonzero(np.abs(delta) > POWER_TOL)),
            "task_tolerance": POWER_TOL,
            "status": "PASS" if not np.any(np.abs(delta) > POWER_TOL) else "FAIL",
        }
    mode_amplitude = group_metrics["all_612"]["boundary_outgoing"]
    rows: list[dict[str, Any]] = []
    for key in keys:
        a = left[key]
        b = right[key]
        ba = _complex(a["outgoing_amplitude_at_boundary"])
        bb = _complex(b["outgoing_amplitude_at_boundary"])
        rows.append({
            "comparison": candidate["label"], "side": key[0], "m": key[1], "n": key[2], "polarization": key[3],
            "propagating": bool(a["propagating"]), "power_carrying": bool(a["power_carrying"]),
            "H15_Y_boundary_re": ba.real, "H15_Y_boundary_im": ba.imag,
            "candidate_boundary_re": bb.real, "candidate_boundary_im": bb.imag,
            "boundary_delta_abs": abs(bb - ba), "H15_Y_R": a["R"], "candidate_R": b["R"],
            "delta_R": float(b["R"]) - float(a["R"]), "H15_Y_T": a["T"], "candidate_T": b["T"],
            "delta_T": float(b["T"]) - float(a["T"]),
        })
    mode_amplitude["task_tolerance"] = MODE_AMPLITUDE_REL_TOL
    mode_amplitude["status"] = "PASS" if mode_amplitude["relative_l2_to_H15_Y"] is not None and mode_amplitude["relative_l2_to_H15_Y"] <= MODE_AMPLITUDE_REL_TOL else "FAIL"
    result = {
        "candidate": candidate["label"],
        "modal_classification_mismatch_counts": class_mismatch,
        "modal_group_metrics": group_metrics,
        "all_mode_boundary_amplitude_task_gate": mode_amplitude,
        "global_power_and_absorption": global_delta,
        "per_propagating_mode_power": propagation_metrics,
        "all_mode_power_deltas": {
            name: {
                "l2_absolute": float(np.linalg.norm(delta)),
                "max_absolute": float(np.max(np.abs(delta))),
                "count_above_1e-6": int(np.count_nonzero(np.abs(delta) > POWER_TOL)),
            }
            for name, delta in per_mode_deltas.items()
        },
    }
    return result, rows


def _field_comparison(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    a = base["samples"]
    b = candidate["samples"]
    coordinate_names = ("x_nm", "y_nm", "z_nm", "interface_z_nm")
    coordinates = {}
    for name in coordinate_names:
        coordinates[name] = {
            "exact_equal": bool(np.array_equal(a[name], b[name])),
            "H15_Y_sha256_le_f64": _canonical_hash(a[name]),
            "candidate_sha256_le_f64": _canonical_hash(b[name]),
            "values": [float(x) for x in a[name]],
        }
        if not coordinates[name]["exact_equal"]:
            raise ValueError(f"sample coordinate mismatch: {name}")
    fields: dict[str, Any] = {}
    for name in ("E_V_per_m", "H_A_per_m"):
        fields[name] = _norm(a[name], b[name])
        fields[name]["task_tolerance"] = FIELD_REL_TOL
        fields[name]["status"] = "PASS" if fields[name]["relative_l2_to_H15_Y"] is not None and fields[name]["relative_l2_to_H15_Y"] <= FIELD_REL_TOL else "FAIL"
        fields[name]["by_component"] = {
            component: _norm(a[name][..., i], b[name][..., i])
            for i, component in enumerate(("x", "y", "z"))
        }
    interfaces = {}
    for name in ("E_t_interface_V_per_m", "H_t_interface_A_per_m"):
        interfaces[name] = _norm(a[name], b[name])
        interfaces[name]["task_tolerance"] = FIELD_REL_TOL
        interfaces[name]["status"] = "PASS" if interfaces[name]["relative_l2_to_H15_Y"] is not None and interfaces[name]["relative_l2_to_H15_Y"] <= FIELD_REL_TOL else "FAIL"
        interfaces[name]["scope"] = "horizontal z planes only, not canonical pillar sidewalls"
    return {
        "coordinate_identity": coordinates,
        "comparison_method": "direct arrays at exact common coordinates; no interpolation and no phase fit",
        "array_shape_z_y_x_component": base["sample_meta"].get("array_shape_z_y_x_component"),
        "H15_Y_archive_sha256": base["sample_meta"].get("archive_sha256"),
        "candidate_archive_sha256": candidate["sample_meta"].get("archive_sha256"),
        "E_H": fields,
        "horizontal_tangential_traces": interfaces,
        "canonical_sidewall_gate": "NOT_MEASURED",
    }


def main() -> None:
    catalog = _read_json(D13_CATALOG)
    h15_catalog = _read_json(RECORDS / "h15_bxyz_saved_output_comparison_v1.json")
    base_catalog = h15_catalog["cases"]["Y"]
    base = _load_run(BASE_LABEL, H15_Y, base_catalog)
    run_cases = {}
    for label, catalog_label in CASE_LABELS.items():
        entry = catalog["cases"][catalog_label]
        run_cases[label] = _load_run(label, Path(entry["run_directory"]), entry)
    for case in run_cases.values():
        if base["physical_identity"] != case["physical_identity"]:
            raise ValueError(f"physical geometry/material/incidence/boundary differs for {case['label']}")
    for case in [base, *run_cases.values()]:
        if case["power"].get("active_mode_count") != 612 or case["power"].get("active_mode_sha256") != MODE_SHA:
            raise ValueError(f"{case['label']} active mode identity mismatch")
        if case["power"].get("dtn_sparse_cutoff_policy") != "scale_homogeneous_relative_only_v1":
            raise ValueError(f"{case['label']} is not the relative-only cutoff run")
        effective_surface_q = (
            case["catalog"].get("surface_quadrature_degree")
            or case["direct_factor_evidence"].get("operator_identity", {}).get("parent_quadrature_degree")
        )
        if effective_surface_q != 28:
            raise ValueError(f"{case['label']} surface q is not 28: {effective_surface_q!r}")
    legacy_catalog = _read_json(RECORDS / "d13_y_y2_y3_relative_cutoff_comparison_v1.json")
    legacy_y3 = legacy_catalog["cases"]["Y3_legacy"]
    pairs: dict[str, Any] = {}
    csv_rows: list[dict[str, Any]] = []
    for label, case in run_cases.items():
        modal, rows = _comparison(base, case)
        csv_rows.extend(rows)
        pairs[label] = {
            "modal_comparison": modal,
            "saved_field_comparison": _field_comparison(base, case),
            "cross_family_scope": "H15-Y versus D13; y and z discretizations both differ, so this is a best-available reference comparison, not a pure single-axis convergence estimate",
        }
    cases = {base["label"]: base, **run_cases}
    identity = {}
    for label, case in cases.items():
        manifest = case["manifest"]
        identity[label] = {
            "run_directory": str(case["run"]),
            "run_id": manifest.get("run_id"),
            "run_manifest_sha256": hashlib.sha256((case["run"] / "run_manifest.json").read_bytes()).hexdigest(),
            "run_summary_sha256": hashlib.sha256((case["run"] / "run_summary.json").read_bytes()).hexdigest(),
            "direct_factor_evidence_sha256": case["direct_factor_evidence_sha256"],
            "summary_status": case["summary"].get("status"),
            "summary_exit_status": case["summary"].get("exit_status"),
            "source_sha": manifest.get("source_sha"),
            "input_sha256": manifest.get("input_sha256"),
            "physical_model_sha256": manifest.get("physical_model_sha256"),
            "resolved_config_sha256": manifest.get("resolved_config_sha256"),
            "axis_cell_counts": case["resolved"]["discretization"]["mesh_axis_cell_counts"],
            "axis_sha256": (
                case["catalog"].get("axis_sha256")
                or case["catalog"].get("actual_mesh_qa", {}).get("axis_sha256_le_f64")
                or case["catalog"].get("mesh", {}).get("axis_sha256_le_f64")
            ),
            "active_mode_count": case["power"].get("active_mode_count"),
            "active_mode_sha256": case["power"].get("active_mode_sha256"),
            "surface_quadrature_degree": case["catalog"].get("surface_quadrature_degree"),
            "volume_quadrature_records": case["catalog"].get("volume_quadrature_records"),
            "cutoff_policy": {
                "effective_policy": case["power"].get("dtn_sparse_cutoff_policy"),
                "relative_tolerance": case["power"].get("dtn_sparse_cutoff_relative_tolerance"),
                "identity_sha256": case["power"].get("dtn_sparse_cutoff_identity_sha256"),
                "catalog_value": case["catalog"].get("cutoff_policy"),
                "direct_factor_evidence_sha256": case["direct_factor_evidence_sha256"],
            },
            "execution_mode": manifest.get("execution_mode"),
            "solver_gates_passed": case["phase"].get("facts", {}).get("passed"),
            "full_dtn_status": case["power"].get("full_dtn_status"),
            "geometry_material_incidence_boundary_sha256": hashlib.sha256(
                json.dumps(case["physical_identity"], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
    payload = {
        "schema": "task40.h15_y_vs_d13_y2_y3_same_relative_only_saved_output_comparison.v2",
        "scope": "offline saved-output comparison only; no FE, factor, VTU, or resource-stream read",
        "physical_identity": "geometry/material/incidence/boundary JSON fields compared exactly across all three runs",
        "mode_identity": {"count": 612, "sha256": MODE_SHA, "keys": "exact side,m,n,polarization; no phase fit"},
        "quadrature": "surface degree 28 and volume q15/default in the referenced run records",
        "sampling": "same x/y/z/interface coordinates required exactly; direct complex arrays; no interpolation or phase fit",
        "same_relative_only_caveat": "H15-Y, D13-Y2, and the corrected D13-Y3 reference all use scale_homogeneous_relative_only_v1. The older absolute-floor D13-Y3 run is retained as historical evidence only and is not used in this corrected comparison.",
        "same_policy_case_catalog": {
            "path": "docs/task40para_phi90_mesh_modes_direct/outcomes/records/d13_y2_y3_same_relative_only_comparison_v1.json",
            "sha256": hashlib.sha256(D13_CATALOG.read_bytes()).hexdigest(),
        },
        "cross_family_caveat": "H15-Y [6,8,10] versus D13-Y2 [6,24,14] and D13-Y3 [6,48,14] changes both y and z discretization; these comparisons do not isolate a single axis",
        "task_thresholds": {
            "global_R_T_A_balance_A_volume_absolute_difference": GLOBAL_POWER_TOL,
            "each_propagating_mode_R_T_absolute_difference": POWER_TOL,
            "same_coordinate_complex_E_H_and_interface_trace_relative_L2": FIELD_REL_TOL,
            "ordered_all_mode_boundary_amplitude_relative_L2": MODE_AMPLITUDE_REL_TOL,
            "canonical_pillar_sidewall": "NOT_MEASURED; horizontal traces do not substitute",
        },
        "cases": identity,
        "comparisons": pairs,
        "historical_y3_legacy_reference_not_used": {
            "run_directory": legacy_y3.get("run_directory"),
            "source_sha": legacy_y3.get("source_sha"),
            "cutoff_policy": legacy_y3.get("cutoff_policy", {}).get("effective_policy"),
            "preserved_in": "d13_y_y2_y3_relative_cutoff_comparison_v1.json and the prior H15 comparison v1 artifacts",
        },
        "limitations": [
            "The H15-Y to D13 comparisons change y and z together and cannot attribute their differences to one axis.",
            "The older absolute-floor D13-Y3 result is retained as history only; the corrected Y3 reference is the same-relative-only run bound above.",
            "Per-run solve gates passing is not equivalent to passing cross-mesh output gates.",
            "All three runs remain finite-R13 and FULL_DTN_NOT_VERIFIED.",
            "Horizontal Ht traces are not canonical pillar sidewall traces.",
        ],
    }
    out_json = RECORDS / "h15_y_vs_d13_y2_y3_same_relative_only_saved_output_comparison_v2.json"
    out_csv = RECORDS / "h15_y_vs_d13_y2_y3_same_relative_only_all_612_modes_v2.csv"
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    columns = list(csv_rows[0]) if csv_rows else []
    with out_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows)
    print(json.dumps({"json": str(out_json), "csv": str(out_csv), "mode_rows": len(csv_rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
