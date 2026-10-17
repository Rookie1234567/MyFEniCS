#!/usr/bin/env python3
"""Compare the completed Task40 H15 B/X/Y/Z outputs offline.

This reads only run manifests, small stage/summary JSON, 612-mode JSON, and the
small saved reference-sample NPZ files.  It does not load VTU, build a mesh,
assemble an operator, or start a solver.  Complex field comparisons use the
stored common coordinates directly, without interpolation or phase fitting.
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
RUNS = {
    "B": "task40_phi90_13p5_H15_B_p6_direct_v1__full3d_direct__mpi1__Mna/20261017T052011.288309Z",
    "X": "task40_phi90_13p5_H15_X_p6_direct_v1__full3d_direct__mpi1__Mna/20261017T053927.852948Z",
    "Y": "task40_phi90_13p5_H15_Y_p6_direct_v1__full3d_direct__mpi1__Mna/20261017T055854.344877Z",
    "Z": "task40_phi90_13p5_H15_Z_p6_direct_v1__full3d_direct__mpi1__Mna/20261017T061913.725631Z",
}
COMPONENTS = ("x", "y", "z")
INTERFACE_COMPONENTS = ("x", "y")


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _mode_key(row: dict[str, Any]) -> tuple[str, int, int, str]:
    return (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"]))


def _complex_pair(value: list[float]) -> complex:
    return complex(float(value[0]), float(value[1]))


def _as_float(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite value in saved output: {value!r}")
    return number


def _axis_hash(values: np.ndarray) -> str:
    canonical = np.ascontiguousarray(np.asarray(values, dtype="<f8"))
    return hashlib.sha256(canonical.tobytes()).hexdigest()


def _mode_key_json(key: tuple[str, int, int, str]) -> dict[str, Any]:
    return {"side": key[0], "m": key[1], "n": key[2], "polarization": key[3]}


def _norm_record(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    ref = np.asarray(reference)
    got = np.asarray(candidate)
    if ref.shape != got.shape:
        raise ValueError(f"shape mismatch: {ref.shape} != {got.shape}")
    if not np.isfinite(ref).all() or not np.isfinite(got).all():
        raise ValueError("non-finite field or modal data")
    delta = got - ref
    ref_norm = float(np.linalg.norm(ref.ravel()))
    delta_norm = float(np.linalg.norm(delta.ravel()))
    flat_index = int(np.argmax(np.abs(delta))) if delta.size else 0
    index = tuple(int(i) for i in np.unravel_index(flat_index, delta.shape)) if delta.size else ()
    return {
        "reference_l2": ref_norm,
        "difference_l2": delta_norm,
        "relative_l2_to_B": delta_norm / ref_norm if ref_norm else None,
        "max_abs_difference": float(np.max(np.abs(delta))) if delta.size else 0.0,
        "max_abs_index": list(index),
    }


def _field_norm_with_location(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    sample: dict[str, np.ndarray],
    component_names: tuple[str, ...] | None = None,
    location_kind: str = "volume",
    fixed_plane_nm: float | None = None,
) -> dict[str, Any]:
    result = _norm_record(reference, candidate)
    index = result["max_abs_index"]
    if location_kind == "volume":
        if len(index) == 4:
            zi, yi, xi, ci = index
            location = {
                "z_nm": float(sample["z_nm"][zi]),
                "y_nm": float(sample["y_nm"][yi]),
                "x_nm": float(sample["x_nm"][xi]),
                "component": component_names[ci] if component_names else str(ci),
            }
        elif len(index) == 3:
            zi, yi, xi = index
            location = {
                "z_nm": float(sample["z_nm"][zi]),
                "y_nm": float(sample["y_nm"][yi]),
                "x_nm": float(sample["x_nm"][xi]),
            }
        else:
            location = {"index": index}
    elif location_kind in {"volume_plane", "interface_plane"}:
        yi, xi, ci = index
        location = {
            "y_nm": float(sample["y_nm"][yi]),
            "x_nm": float(sample["x_nm"][xi]),
            "component": component_names[ci] if component_names else str(ci),
        }
        if location_kind == "volume_plane":
            location["z_nm"] = fixed_plane_nm
        else:
            location["interface_z_nm"] = fixed_plane_nm
    elif location_kind == "interface":
        ii, yi, xi, ci = index
        location = {
            "interface_z_nm": float(sample["interface_z_nm"][ii]),
            "y_nm": float(sample["y_nm"][yi]),
            "x_nm": float(sample["x_nm"][xi]),
            "component": component_names[ci] if component_names else str(ci),
        }
    else:
        raise ValueError(f"unknown field location kind {location_kind!r}")
    result["max_abs_location"] = location
    return result


def _read_case(label: str) -> dict[str, Any]:
    run = RESULTS / RUNS[label]
    output = run / "numerical_output"
    manifest = _json(run / "run_manifest.json")
    phase = _json(run / "workflow_phase.json")
    summary = _json(run / "run_summary.json")
    if phase.get("phase") != "complete" or phase.get("facts", {}).get("passed") is not True:
        raise ValueError(f"H15-{label} is not a passed terminal run")
    authority = summary.get("resource_authority", {})
    if (
        summary.get("status") != "finished"
        or summary.get("exit_status") != 0
        or authority.get("descendants_cleared") is not True
    ):
        raise ValueError(f"H15-{label} is not naturally finished and cleared")

    mesh_qa: dict[str, Any] | None = None
    residual: dict[str, Any] | None = None
    solve: dict[str, Any] | None = None
    surface_contract: dict[str, Any] | None = None
    for line in (run / "stages.jsonl").open(encoding="utf-8"):
        event = json.loads(line)
        stage = event.get("stage", "")
        facts = event.get("facts", {})
        if stage == "p6_direct_actual_mesh_qa_complete":
            mesh_qa = facts
        elif stage.endswith("_residual_complete") and stage.startswith("p6_direct_A6_"):
            residual = facts
        elif stage == "p6_direct_materialized_solve_complete":
            solve = facts
        elif stage == "p6_direct_surface_carrier_complete":
            surface_contract = facts
    if not mesh_qa or mesh_qa.get("status") != "PASS":
        raise ValueError(f"H15-{label} lacks passing actual mesh QA")
    if not residual or residual.get("finite") is not True:
        raise ValueError(f"H15-{label} lacks finite independent A6/condensed evidence")

    port_payload = _json(output / "dtn_port_diffraction_orders_3d.json")
    power = _json(output / "dtn_port_power_metrics_3d.json")
    volume = _json(output / "volume_absorption.json")
    sample_meta = _json(output / "full3d_reference_samples.json")
    with np.load(output / "full3d_reference_samples.npz", allow_pickle=False) as archive:
        samples = {key: archive[key].copy() for key in archive.files}
    orders = port_payload["orders"]
    keyed = {_mode_key(row): row for row in orders}
    if len(orders) != 612 or len(keyed) != 612:
        raise ValueError(f"H15-{label} does not have 612 unique active modes")
    if power.get("active_mode_sha256") != "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e":
        raise ValueError(f"H15-{label} mode identity mismatch")
    return {
        "label": label,
        "run": run,
        "output": output,
        "manifest": manifest,
        "phase": phase,
        "summary": summary,
        "authority": authority,
        "mesh_qa": mesh_qa,
        "residual": residual,
        "solve": solve,
        "surface_contract": surface_contract,
        "orders": orders,
        "keyed_orders": keyed,
        "power": power,
        "volume": volume,
        "sample_meta": sample_meta,
        "samples": samples,
    }


def _mode_group_summary(
    base: dict[tuple[str, int, int, str], dict[str, Any]],
    candidate: dict[tuple[str, int, int, str], dict[str, Any]],
    keys: list[tuple[str, int, int, str]],
) -> dict[str, Any]:
    b_boundary = np.array([_complex_pair(base[key]["outgoing_amplitude_at_boundary"]) for key in keys])
    c_boundary = np.array([_complex_pair(candidate[key]["outgoing_amplitude_at_boundary"]) for key in keys])
    b_raw = np.array([_complex_pair(base[key]["outgoing_amplitude"]) for key in keys])
    c_raw = np.array([_complex_pair(candidate[key]["outgoing_amplitude"]) for key in keys])
    boundary = _norm_record(b_boundary, c_boundary)
    raw = _norm_record(b_raw, c_raw)
    difference = np.abs(c_boundary - b_boundary)
    max_position = int(np.argmax(difference)) if difference.size else 0
    return {
        "mode_count": len(keys),
        "boundary_outgoing": boundary,
        "raw_outgoing_reference_plane": raw,
        "max_boundary_mode": _mode_key_json(keys[max_position]) if keys else None,
    }


def _scalar_delta(base: float, candidate: float) -> dict[str, float | None]:
    delta = candidate - base
    return {
        "H15_B": base,
        "case": candidate,
        "delta_case_minus_B": delta,
        "relative_delta_to_B": delta / base if base else None,
    }


def _compare_modes(
    label: str,
    base_case: dict[str, Any],
    case: dict[str, Any],
    csv_writer: csv.DictWriter,
) -> dict[str, Any]:
    base = base_case["keyed_orders"]
    candidate = case["keyed_orders"]
    if set(base) != set(candidate):
        raise ValueError(f"H15-{label} has a different modal key set")
    keys = sorted(base, key=lambda k: (k[0], k[1], k[2], k[3]))
    mismatch_counts = {
        name: sum(bool(base[k].get(name)) != bool(candidate[k].get(name)) for k in keys)
        for name in ("propagating", "power_carrying", "rayleigh_warning")
    }
    if any(mismatch_counts.values()):
        raise ValueError(f"H15-{label} modal classification changed: {mismatch_counts}")
    groups = {
        "all": keys,
        "top": [k for k in keys if k[0] == "top"],
        "bottom": [k for k in keys if k[0] == "bottom"],
        "propagating": [k for k in keys if base[k]["propagating"]],
        "power_carrying": [k for k in keys if base[k]["power_carrying"]],
        "evanescent": [k for k in keys if not base[k]["propagating"]],
        "non_power_carrying": [k for k in keys if not base[k]["power_carrying"]],
    }
    group_metrics = {
        name: _mode_group_summary(base, candidate, members)
        for name, members in groups.items()
    }
    r_delta = np.array([float(candidate[k]["R"]) - float(base[k]["R"]) for k in keys])
    t_delta = np.array([float(candidate[k]["T"]) - float(base[k]["T"]) for k in keys])
    max_r = int(np.argmax(np.abs(r_delta)))
    max_t = int(np.argmax(np.abs(t_delta)))
    for key in keys:
        b = base[key]
        c = candidate[key]
        b_boundary = _complex_pair(b["outgoing_amplitude_at_boundary"])
        c_boundary = _complex_pair(c["outgoing_amplitude_at_boundary"])
        b_raw = _complex_pair(b["outgoing_amplitude"])
        c_raw = _complex_pair(c["outgoing_amplitude"])
        csv_writer.writerow(
            {
                "case": label,
                "side": key[0],
                "m": key[1],
                "n": key[2],
                "polarization": key[3],
                "propagating": bool(b["propagating"]),
                "power_carrying": bool(b["power_carrying"]),
                "B_boundary_re": b_boundary.real,
                "B_boundary_im": b_boundary.imag,
                "case_boundary_re": c_boundary.real,
                "case_boundary_im": c_boundary.imag,
                "boundary_delta_abs": abs(c_boundary - b_boundary),
                "boundary_delta_rel_to_B_mode": abs(c_boundary - b_boundary) / abs(b_boundary) if abs(b_boundary) else "",
                "B_raw_outgoing_re": b_raw.real,
                "B_raw_outgoing_im": b_raw.imag,
                "case_raw_outgoing_re": c_raw.real,
                "case_raw_outgoing_im": c_raw.imag,
                "B_R": b["R"],
                "case_R": c["R"],
                "delta_R": float(c["R"]) - float(b["R"]),
                "B_T": b["T"],
                "case_T": c["T"],
                "delta_T": float(c["T"]) - float(b["T"]),
            }
        )
    metric_keys = ("R_total", "R00_s", "R00_total", "T_total", "A_balance")
    global_metrics = {
        name: _scalar_delta(_as_float(base_case["power"][name]), _as_float(case["power"][name]))
        for name in metric_keys
    }
    global_metrics["A_volume_total"] = _scalar_delta(
        _as_float(base_case["volume"]["A_volume_total"]),
        _as_float(case["volume"]["A_volume_total"]),
    )
    global_metrics["energy_closure_error"] = _scalar_delta(
        _as_float(base_case["volume"]["energy_closure_error_port_volume"]),
        _as_float(case["volume"]["energy_closure_error_port_volume"]),
    )
    return {
        "case": label,
        "changed_axis_from_B": case["mesh_qa"]["changed_axis"],
        "mode_key_count": len(keys),
        "classification_mismatch_counts": mismatch_counts,
        "group_metrics": group_metrics,
        "per_mode_power_delta": {
            "R_l2_abs": float(np.linalg.norm(r_delta)),
            "T_l2_abs": float(np.linalg.norm(t_delta)),
            "R_max_abs": float(abs(r_delta[max_r])),
            "R_max_key": _mode_key_json(keys[max_r]),
            "T_max_abs": float(abs(t_delta[max_t])),
            "T_max_key": _mode_key_json(keys[max_t]),
            "sum_R_delta": float(np.sum(r_delta)),
            "sum_T_delta": float(np.sum(t_delta)),
        },
        "global_metrics": global_metrics,
    }


def _compare_fields(
    base_case: dict[str, Any], case: dict[str, Any]
) -> dict[str, Any]:
    base = base_case["samples"]
    candidate = case["samples"]
    coordinates = ("x_nm", "y_nm", "z_nm", "interface_z_nm")
    coordinate_identity = {
        key: {
            "exact_equal": bool(np.array_equal(base[key], candidate[key])),
            "sha256_le_f64": _axis_hash(base[key]),
            "values": [float(v) for v in base[key]],
        }
        for key in coordinates
    }
    if not all(item["exact_equal"] for item in coordinate_identity.values()):
        raise ValueError("saved field samples are not at identical coordinates")
    fields: dict[str, Any] = {}
    for name, names in (("E_V_per_m", COMPONENTS), ("H_A_per_m", COMPONENTS)):
        a = base[name]
        b = candidate[name]
        fields[name] = {
            "all_points_and_components": _field_norm_with_location(a, b, sample=base, component_names=names),
            "by_component": {
                component: _field_norm_with_location(
                    a[..., i], b[..., i], sample=base, location_kind="volume"
                )
                for i, component in enumerate(names)
            },
            "by_z_plane": {
                str(float(base["z_nm"][i])): _field_norm_with_location(
                    a[i],
                    b[i],
                    sample=base,
                    component_names=names,
                    location_kind="volume_plane",
                    fixed_plane_nm=float(base["z_nm"][i]),
                )
                for i in range(a.shape[0])
            },
        }
    interfaces: dict[str, Any] = {}
    for name in ("E_t_interface_V_per_m", "H_t_interface_A_per_m"):
        a = base[name]
        b = candidate[name]
        interfaces[name] = {
            "all_saved_horizontal_trace_planes": _field_norm_with_location(
                a,
                b,
                sample=base,
                component_names=INTERFACE_COMPONENTS,
                location_kind="interface",
            ),
            "by_z_plane": {
                str(float(base["interface_z_nm"][i])): _field_norm_with_location(
                    a[i],
                    b[i],
                    sample=base,
                    component_names=INTERFACE_COMPONENTS,
                    location_kind="interface_plane",
                    fixed_plane_nm=float(base["interface_z_nm"][i]),
                )
                for i in range(a.shape[0])
            },
            "interpretation": "saved horizontal z-plane tangential traces; not canonical pillar sidewalls",
        }
    return {
        "coordinates": coordinate_identity,
        "interpolation_or_phase_fit": "none; direct comparison at exactly equal saved coordinates",
        "sample_arrays": {
            "grid_convention": base_case["sample_meta"]["grid_convention"],
            "shape_z_y_x_component": base_case["sample_meta"]["array_shape_z_y_x_component"],
            "reference_archive_sha256": base_case["sample_meta"]["archive_sha256"],
            "case_archive_sha256": case["sample_meta"]["archive_sha256"],
        },
        "E_H": fields,
        "horizontal_interface_tangential_fields": interfaces,
    }


def main() -> None:
    RECORDS.mkdir(parents=True, exist_ok=True)
    cases = {label: _read_case(label) for label in "BXYZ"}
    base = cases["B"]
    keys_b = set(base["keyed_orders"])
    if len(keys_b) != 612:
        raise ValueError("base mode set is not 612")
    csv_path = RECORDS / "h15_bxyz_all_612_modes_v1.csv"
    columns = [
        "case", "side", "m", "n", "polarization", "propagating", "power_carrying",
        "B_boundary_re", "B_boundary_im", "case_boundary_re", "case_boundary_im",
        "boundary_delta_abs", "boundary_delta_rel_to_B_mode", "B_raw_outgoing_re",
        "B_raw_outgoing_im", "case_raw_outgoing_re", "case_raw_outgoing_im",
        "B_R", "case_R", "delta_R", "B_T", "case_T", "delta_T",
    ]
    comparisons = {}
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for label in "XYZ":
            case = cases[label]
            comparisons[f"B_vs_{label}"] = {
                "modal_outputs": _compare_modes(label, base, case, writer),
                "saved_fields": _compare_fields(base, case),
            }

    case_summary: dict[str, Any] = {}
    for label in "BXYZ":
        case = cases[label]
        manifest = case["manifest"]
        qa = case["mesh_qa"]
        authority = case["authority"]
        case_summary[label] = {
            "run_directory": str(case["run"]),
            "run_id": manifest.get("run_id"),
            "source_sha": manifest.get("source_sha"),
            "input_sha256": manifest.get("input_sha256"),
            "physical_model_sha256": manifest.get("physical_model_sha256"),
            "resolved_config_sha256": manifest.get("resolved_config_sha256"),
            "execution_mode": manifest.get("execution_mode"),
            "actual_mesh_qa": qa,
            "mode_count": case["power"].get("active_mode_count"),
            "mode_sha256": case["power"].get("active_mode_sha256"),
            "surface_quadrature_degree": (
                case["surface_contract"].get("parent_quadrature_degree")
                if case["surface_contract"]
                else None
            ),
            "actual_global_cell_count": qa.get("actual_global_cell_count"),
            "volume_quadrature_records": case["surface_contract"].get("volume_quadrature_records") if case["surface_contract"] else None,
            "numerical_gates": {
                "passed": case["phase"]["facts"]["passed"],
                "condensed_relative": case["residual"]["condensed_direct_relative"],
                "condensed_gate": case["residual"]["condensed_direct_residual_gate"],
                "original_A6_relative": case["residual"]["original_A6_active_rectangle_relative"],
                "original_A6_gate": case["residual"]["original_A6_active_rectangle_relative_gate"],
                "same_factor_correction_count": case["residual"]["same_factor_correction_count"],
                "same_factor_correction_max": case["residual"]["max_same_factor_corrections"],
                "energy_closure_error_port_volume": case["volume"]["energy_closure_error_port_volume"],
                "A_volume_total": case["volume"]["A_volume_total"],
                "R_total": case["power"]["R_total"],
                "T_total": case["power"]["T_total"],
                "A_balance": case["power"]["A_balance"],
                "full_dtn_status": case["power"].get("full_dtn_status"),
            },
            "resources": {
                "elapsed_seconds": authority.get("elapsed_seconds"),
                "tree_rss_peak_bytes": authority.get("sampled_process_tree_rss_peak_bytes"),
                "tree_swap_peak_bytes": authority.get("sampled_process_tree_swap_peak_bytes"),
                "task_swap_activity": authority.get("job_swap_activity"),
                "global_swap_delta_observe_only": authority.get("global_swap_activity", {}).get("delta"),
                "pss_status": authority.get("pss_status"),
                "fixed_rss_cap_bytes": authority.get("rss_hard_limit_bytes"),
                "host_available_floor_bytes": authority.get("minimum_available_bytes"),
                "launch_effective_available_bytes": authority.get("launch_envelope", {}).get("effective_available_bytes"),
                "runtime_minimum_available_bytes": None,
                "runtime_minimum_note": "not aggregated; launch envelope is only a launch-time snapshot",
            },
        }

    payload = {
        "schema": "task40.h15_bxyz_saved_output_comparison.v1",
        "source_sha": "d9edbcd583bb74dde36e3c9552893560f47bd230",
        "comparison_basis": "H15-B versus one-axis X/Y/Z refinements, same finite 612-mode R13 rectangle, q28 surface/q15 default volume, same relative-only policy",
        "mode_comparison": "exact (side,m,n,polarization) key alignment; all 612 modes; no phase fit",
        "field_comparison": "same stored x/y/z coordinates; direct complex E/H and saved horizontal Et/Ht samples; no interpolation or phase fit",
        "cases": case_summary,
        "comparisons": comparisons,
        "limitations": [
            "These runs compare finite R13 operators and do not verify full DtN.",
            "The saved Et/Ht arrays are horizontal z-plane traces, not canonical pillar sidewalls.",
            "A small B/Z difference only compares those two z resolutions; it does not prove a still coarser z grid is accurate.",
            "The very large B/Y difference shows substantial y sensitivity at H15; directional changes are not interchangeable.",
            "Evanescent raw outgoing coefficients can be dominated by reference-plane exponential scaling; boundary-phase-scaled outgoing amplitudes are reported separately.",
            "The per-run energy closure is a solve/energy check, not a mesh-convergence certificate.",
        ],
    }
    json_path = RECORDS / "h15_bxyz_saved_output_comparison_v1.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "mode_rows": 3 * 612}, sort_keys=True))


if __name__ == "__main__":
    main()
