#!/usr/bin/env python3
"""Offline comparison of the saved D07C G3 M8/N64 and M8/N96 runs.

This reads only each run's small direct summary, modal-orders JSON, sample
metadata, and 1.35 MB reference-sample NPZ. It does not read VTU/resources or
construct a mesh, carrier, matrix, factor, or FE solve.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
OUTCOMES = Path(
    os.environ.get(
        "TASK40_D07C_COMPARISON_OUTCOMES",
        ROOT / "docs/task40para_phi90_mesh_modes_direct/outcomes",
    )
)
BASE = Path(
    os.environ.get("TASK40_D07C_RESULTS_ROOT", ROOT / "results")
) / "si_block_phi90_50x50_17x20_h120"
CASES = {
    "N64": {
        "directory": "task40para_phi90_0p7_D07C_G3_M8_N64_p6_direct_v1__full3d_direct__mpi1__Mna",
        "run": "20261030T132407.592584Z",
    },
    "N96": {
        "directory": "task40para_phi90_0p7_D07C_G3_M8_N96_p6_direct_v1__full3d_direct__mpi1__Mna",
        "run": "20261030T234947.703061Z",
    },
}
GLOBAL_LIMIT = 1e-5
MODE_LIMIT = 1e-6
FIELD_LIMIT = 1e-4


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def c128(pair: list[float]) -> complex:
    return complex(float(pair[0]), float(pair[1]))


def l2_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    ref = np.asarray(reference)
    cand = np.asarray(candidate)
    if ref.shape != cand.shape:
        raise ValueError(f"sample shape mismatch: {ref.shape} != {cand.shape}")
    if not np.isfinite(ref).all() or not np.isfinite(cand).all():
        raise ValueError("non-finite field sample")
    delta = cand - ref
    ref_norm = float(np.linalg.norm(ref.ravel()))
    delta_norm = float(np.linalg.norm(delta.ravel()))
    return {
        "reference_l2": ref_norm,
        "delta_l2": delta_norm,
        "relative_l2_reference_denominator": delta_norm / ref_norm if ref_norm else None,
        "max_abs_delta": float(np.max(np.abs(delta))) if delta.size else 0.0,
    }


def load_case(name: str) -> dict[str, Any]:
    spec = CASES[name]
    run_dir = BASE / spec["directory"] / spec["run"]
    summary_path = run_dir / "p6_condensed_direct_summary.json"
    manifest_path = run_dir / "run_manifest.json"
    orders_path = run_dir / "numerical_output/dtn_port_diffraction_orders_3d.json"
    samples_meta_path = run_dir / "numerical_output/full3d_reference_samples.json"
    samples_path = run_dir / "numerical_output/full3d_reference_samples.npz"
    summary = read_json(summary_path)
    manifest = read_json(manifest_path)
    orders_doc = read_json(orders_path)
    orders_list = orders_doc["orders"]
    orders = {
        (str(x["side"]), int(x["m"]), int(x["n"]), str(x["polarization"])): x
        for x in orders_list
    }
    if len(orders) != len(orders_list):
        raise ValueError(f"duplicate signed mode key in {name}")
    with np.load(samples_path) as archive:
        samples = {key: archive[key].copy() for key in archive.files}
    for key in ("R", "T"):
        if not all(np.isfinite(float(x[key])) for x in orders.values()):
            raise ValueError(f"non-finite modal {key} in {name}")
    for x in orders.values():
        for key in ("outgoing_amplitude_at_boundary", "boundary_phase", "kz", "beta"):
            values = np.asarray(x[key], dtype=np.float64)
            if not np.isfinite(values).all():
                raise ValueError(f"non-finite {key} in {name}")
    return {
        "name": name,
        "run_dir": run_dir,
        "summary": summary,
        "manifest": manifest,
        "orders": orders,
        "samples_meta": read_json(samples_meta_path),
        "samples": samples,
        "files": {
            "run_manifest.json": {"path": str(manifest_path), "sha256": sha256(manifest_path), "bytes": manifest_path.stat().st_size},
            "p6_condensed_direct_summary.json": {"path": str(summary_path), "sha256": sha256(summary_path), "bytes": summary_path.stat().st_size},
            "dtn_port_diffraction_orders_3d.json": {"path": str(orders_path), "sha256": sha256(orders_path), "bytes": orders_path.stat().st_size},
            "full3d_reference_samples.json": {"path": str(samples_meta_path), "sha256": sha256(samples_meta_path), "bytes": samples_meta_path.stat().st_size},
            "full3d_reference_samples.npz": {"path": str(samples_path), "sha256": sha256(samples_path), "bytes": samples_path.stat().st_size},
        },
    }


def key_json(key: tuple[str, int, int, str]) -> dict[str, Any]:
    return {"side": key[0], "m": key[1], "n": key[2], "polarization": key[3]}


def max_modal_delta(
    keys: list[tuple[str, int, int, str]],
    ref: dict[tuple[str, int, int, str], dict[str, Any]],
    cand: dict[tuple[str, int, int, str], dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    values: list[tuple[float, tuple[str, int, int, str], float, float, bool]] = []
    for key in keys:
        candidate = float(cand[key][field])
        measured = key in ref
        reference = float(ref[key][field]) if measured else 0.0
        values.append((abs(candidate - reference), key, candidate, reference, measured))
    if not values:
        return {"value": 0.0, "key": None, "N64_measured": False}
    value, key, candidate, reference, measured = max(values, key=lambda x: x[0])
    return {
        "value": value,
        "key": key_json(key),
        "N96": candidate,
        "N64_or_zero_extension": reference,
        "N64_value_measured": measured,
    }


def boundary_l2(
    keys: list[tuple[str, int, int, str]],
    ref: dict[tuple[str, int, int, str], dict[str, Any]],
    cand: dict[tuple[str, int, int, str], dict[str, Any]],
) -> dict[str, Any]:
    r = np.fromiter(
        (c128(ref[k]["outgoing_amplitude_at_boundary"]) if k in ref else 0j for k in keys),
        dtype=np.complex128,
        count=len(keys),
    )
    c = np.fromiter(
        (c128(cand[k]["outgoing_amplitude_at_boundary"]) for k in keys),
        dtype=np.complex128,
        count=len(keys),
    )
    metrics = l2_metrics(r, c)
    delta = c - r
    max_i = int(np.argmax(np.abs(delta))) if delta.size else 0
    metrics.update({
        "key_count": len(keys),
        "N64_missing_keys_zero_extended_for_diagnostic": sum(k not in ref for k in keys),
        "max_abs_delta_key": key_json(keys[max_i]) if keys else None,
        "comparison": "outgoing_amplitude_at_boundary; no phase fit",
    })
    return metrics


def main() -> None:
    n64, n96 = load_case("N64"), load_case("N96")
    s64, s96 = n64["summary"], n96["summary"]
    m64, m96 = n64["manifest"], n96["manifest"]
    op64, op96 = s64["operator_identity"], s96["operator_identity"]
    keys64, keys96 = set(n64["orders"]), set(n96["orders"])
    if not keys64 <= keys96:
        raise ValueError("N64 mode keys are not a subset of N96")
    added = keys96 - keys64
    if len(keys64) != 4488 or len(keys96) != 6664 or len(added) != 2176:
        raise ValueError("unexpected signed mode counts")

    # Confirm all unchanged numerical geometry/physics/quadrature identities.
    if m64["physical_model_sha256"] != m96["physical_model_sha256"]:
        raise ValueError("physical model identity differs")
    mesh64, mesh96 = s64["mesh_evidence"], s96["mesh_evidence"]
    if mesh64["axis_sha256_le_f64"] != mesh96["axis_sha256_le_f64"]:
        raise ValueError("axis identity differs")
    for key in ("actual_global_cell_count", "material_tag_counts", "expected_material_tag_counts"):
        if mesh64[key] != mesh96[key]:
            raise ValueError(f"mesh identity differs at {key}")
    for key in ("degree", "parent_quadrature_degree", "volume_quadrature_records", "dtn_sparse_cutoff_policy", "dtn_sparse_cutoff_relative_tolerance"):
        if op64[key] != op96[key]:
            raise ValueError(f"operator identity differs at {key}")
    for key in keys64:
        for field in ("propagating", "power_carrying", "beta", "kz", "boundary_phase", "medium", "direction", "vertical_sign"):
            if n64["orders"][key][field] != n96["orders"][key][field]:
                raise ValueError(f"common mode identity differs: {key} / {field}")
    if any(not (-8 <= k[1] <= 8 and -96 <= k[2] <= 1) for k in keys96):
        raise ValueError("N96 key escaped declared finite rectangle")
    if any(k[2] < -96 or k[2] > -65 for k in added):
        raise ValueError("unexpected N96-only n-index range")
    if not all(n96["orders"][k]["propagating"] and n96["orders"][k]["power_carrying"] for k in added):
        raise ValueError("added N96 keys are not all propagating and power-carrying")

    counts = {
        name: {
            "all": len(case["orders"]),
            "propagating": sum(bool(x["propagating"]) for x in case["orders"].values()),
            "power_carrying": sum(bool(x["power_carrying"]) for x in case["orders"].values()),
        }
        for name, case in (("N64", n64), ("N96", n96))
    }
    scopes = {
        "all_N96_keys_with_N64_zero_extension": sorted(keys96),
        "common_measured_keys": sorted(keys64),
        "power_carrying_N96": sorted(k for k in keys96 if n96["orders"][k]["power_carrying"]),
        "propagating_N96": sorted(k for k in keys96 if n96["orders"][k]["propagating"]),
        "N96_added_keys": sorted(added),
    }
    modal_deltas: dict[str, Any] = {}
    for scope, keys in scopes.items():
        entry = {"count": len(keys)}
        for field in ("R", "T"):
            delta = max_modal_delta(keys, n64["orders"], n96["orders"], field)
            entry[f"max_abs_delta_{field}"] = delta
            if scope in ("all_N96_keys_with_N64_zero_extension", "power_carrying_N96"):
                entry[f"{field}_limit"] = MODE_LIMIT
                entry[f"{field}_pass"] = delta["value"] <= MODE_LIMIT
        modal_deltas[scope] = entry

    # Verify exact coordinate equality before comparing complex field samples.
    samples64, samples96 = n64["samples"], n96["samples"]
    coordinate_keys = ("x_nm", "y_nm", "z_nm", "interface_z_nm")
    if any(not np.array_equal(samples64[k], samples96[k]) for k in coordinate_keys):
        raise ValueError("sample coordinate arrays differ")
    fields: dict[str, Any] = {}
    for field in ("E_V_per_m", "H_A_per_m", "E_t_interface_V_per_m", "H_t_interface_A_per_m"):
        metrics = l2_metrics(samples64[field], samples96[field])
        metrics.update({"limit": FIELD_LIMIT, "pass": metrics["relative_l2_reference_denominator"] <= FIELD_LIMIT})
        fields[field] = metrics
    per_plane: dict[str, Any] = {}
    for field in ("E_V_per_m", "H_A_per_m"):
        per_plane[field] = {
            str(float(z)): l2_metrics(samples64[field][i], samples96[field][i])
            for i, z in enumerate(samples64["z_nm"])
        }
    sample_meta64, sample_meta96 = n64["samples_meta"], n96["samples_meta"]
    if sample_meta64["interface_plane_indices"] != sample_meta96["interface_plane_indices"]:
        raise ValueError("interface sample plane indices differ")

    official64 = s64["official_result"]
    official96 = s96["official_result"]
    global_fields = {
        "R_total": ("port_metrics", "R_total"),
        "T_total": ("port_metrics", "T_total"),
        "A_balance": ("port_metrics", "A_balance"),
        "A_volume_total": ("volume_metrics", "A_volume_total"),
    }
    global_deltas: dict[str, Any] = {}
    for name, (group, field) in global_fields.items():
        value64 = float(official64[group][field])
        value96 = float(official96[group][field])
        delta = value96 - value64
        global_deltas[name] = {
            "N64": value64,
            "N96": value96,
            "signed_delta_N96_minus_N64": delta,
            "absolute_delta": abs(delta),
            "limit": GLOBAL_LIMIT,
            "pass": abs(delta) <= GLOBAL_LIMIT,
        }
    named_channels: dict[str, Any] = {}
    for name, value64, value96 in (
        ("R00_s", official64["port_metrics"]["R00_s"], official96["port_metrics"]["R00_s"]),
        ("R00_total", official64["port_metrics"]["R00_total"], official96["port_metrics"]["R00_total"]),
    ):
        delta = float(value96) - float(value64)
        named_channels[name] = {
            "N64": float(value64),
            "N96": float(value96),
            "signed_delta_N96_minus_N64": delta,
            "absolute_delta": abs(delta),
            "limit": MODE_LIMIT,
            "pass": abs(delta) <= MODE_LIMIT,
            "signed_mode_key": key_json(("top", 0, 0, "s")) if name == "R00_s" else None,
        }

    boundary_all = boundary_l2(sorted(keys96), n64["orders"], n96["orders"])
    boundary_all.update({"limit": FIELD_LIMIT, "pass": boundary_all["relative_l2_reference_denominator"] <= FIELD_LIMIT})
    boundary_common = boundary_l2(sorted(keys64), n64["orders"], n96["orders"])
    boundary_added = boundary_l2(sorted(added), {}, n96["orders"])
    # boundary_added has zero reference norm, so it is intentionally an absolute diagnostic only.

    rta64 = official64["port_metrics"]
    rta96 = official96["port_metrics"]
    result = {
        "schema": "task40.d07c.g3.m8.n64_n96_saved_output_comparison.v1",
        "comparison": {
            "reference": "G3 M8/N64",
            "candidate": "G3 M8/N96",
            "mode_identity": "N64 signed mode keys are a verified subset of N96; common beta/kz/boundary-phase and propagation/power classifications match exactly.",
            "missing_reference_semantics": "N64 has no measured values for 2,176 N96-added keys. A separate mathematical zero-extension diagnostic is used for full-candidate-set mode and boundary comparisons; missing reference data are not represented as measured zeros.",
            "phase_fit": False,
            "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
            "canonical_sidewall": "NOT_MEASURED",
        },
        "run_identity": {
            name: {
                "run_id": case["manifest"]["run_id"],
                "run_directory": str(case["run_dir"]),
                "source_sha": case["manifest"]["source_sha"],
                "input_sha256": case["manifest"]["input_sha256"],
                "physical_model_sha256": case["manifest"]["physical_model_sha256"],
                "resolved_config_sha256": case["manifest"]["resolved_config_sha256"],
                "status": case["manifest"]["status"],
                "exit_status": case["manifest"]["exit_status"],
                "mesh_axis_sha256_le_f64": case["summary"]["mesh_evidence"]["axis_sha256_le_f64"],
                "mode_count": case["summary"]["operator_identity"]["active_mode_count"],
                "mode_sha256": case["summary"]["operator_identity"]["active_mode_sha256"],
                "surface_quadrature": case["summary"]["operator_identity"]["parent_quadrature_degree"],
                "volume_quadrature_records": case["summary"]["operator_identity"]["volume_quadrature_records"],
                "sparse_cutoff_policy": case["summary"]["operator_identity"]["dtn_sparse_cutoff_policy"],
                "sparse_cutoff_relative_tolerance": case["summary"]["operator_identity"]["dtn_sparse_cutoff_relative_tolerance"],
                "files": case["files"],
            }
            for name, case in (("N64", n64), ("N96", n96))
        },
        "fixed_identity_checks": {
            "physical_model_equal": m64["physical_model_sha256"] == m96["physical_model_sha256"],
            "axes_equal": mesh64["axis_sha256_le_f64"] == mesh96["axis_sha256_le_f64"],
            "cell_count": mesh96["actual_global_cell_count"],
            "material_tags_equal": mesh64["material_tag_counts"] == mesh96["material_tag_counts"],
            "volume_q15_default_equal": op64["volume_quadrature_records"] == op96["volume_quadrature_records"],
            "surface_q81_equal": op64["parent_quadrature_degree"] == op96["parent_quadrature_degree"] == 81,
            "relative_only_cutoff_equal": op64["dtn_sparse_cutoff_policy"] == op96["dtn_sparse_cutoff_policy"] == "scale_homogeneous_relative_only_v1",
            "sample_coordinates_exactly_equal": True,
            "source_equal": m64["source_sha"] == m96["source_sha"],
            "input_equal": m64["input_sha256"] == m96["input_sha256"],
        },
        "mode_counts": {
            **counts,
            "N96_added_vs_N64": len(added),
            "added_range": {"m": [-8, 8], "n": [-96, -65]},
            "added_propagating": sum(bool(n96["orders"][k]["propagating"]) for k in added),
            "added_power_carrying": sum(bool(n96["orders"][k]["power_carrying"]) for k in added),
            "auto_inventory_propagating_modes": 64120,
            "auto_inventory_propagating_not_in_N96": 64120 - counts["N96"]["propagating"],
        },
        "global_observables": global_deltas,
        "named_channel_observables": named_channels,
        "modal_R_T": modal_deltas,
        "boundary_complex_amplitude_outgoing": {
            "metric": "outgoing_amplitude_at_boundary complex L2; no phase alignment or fit",
            "all_N96_with_N64_zero_extension": boundary_all,
            "common_measured_keys_only": boundary_common,
            "added_N96_keys_vs_zero": boundary_added,
        },
        "sampled_complex_fields": {
            "metadata": {
                "coordinate_arrays": {k: samples64[k].tolist() if k in ("z_nm", "interface_z_nm") else {"count": int(samples64[k].size), "first": float(samples64[k][0]), "last": float(samples64[k][-1])} for k in coordinate_keys},
                "plane_z_nm": [float(x) for x in samples64["z_nm"]],
                "horizontal_interface_planes_z_nm": [float(samples64["z_nm"][i]) for i in sample_meta64["interface_plane_indices"]],
                "relative_denominator": "N64 sample norm",
                "phase_fit": False,
            },
            "overall": fields,
            "per_plane_E": per_plane["E_V_per_m"],
            "per_plane_H": per_plane["H_A_per_m"],
            "interpretation": "E_t/H_t are horizontal z-plane interface diagnostics at the saved sample planes; they are not canonical grating sidewall traces.",
        },
        "single_run_gates": {
            "N64_passed": s64["passed"],
            "N96_passed": s96["passed"],
            "N64_condensed_residual": s64["residuals"]["condensed_direct_relative"],
            "N96_condensed_residual": s96["residuals"]["condensed_direct_relative"],
            "N64_original_A6_active_rectangle_relative": s64["residuals"]["original_A6_active_rectangle_relative"],
            "N96_original_A6_active_rectangle_relative": s96["residuals"]["original_A6_active_rectangle_relative"],
            "N64_energy_closure_signed": official64["energy_closure_error_port_volume"],
            "N96_energy_closure_signed": official96["energy_closure_error_port_volume"],
            "scope_note": "These are finite active-rectangle A6 checks; they do not verify the omitted parent DtN modes.",
        },
        "limitations": [
            "N64 and N96 source and input identities differ as expected for the mode-window change; each run is independently solved and no FE object/factor is shared.",
            "The comparison covers finite N64 and N96 rectangles only. N96 includes 6,664 modes but the automatic propagating inventory has 64,120; 57,584 propagating modes remain outside N96.",
            "Mathematical zero extension is explicitly diagnostic for the 2,176 N96-only keys; their N64 amplitudes/powers were not measured.",
            "Horizontal E_t/H_t samples do not close canonical sidewall trace requirements.",
            "FULL_DTN_NOT_VERIFIED and canonical sidewall NOT_MEASURED remain in force.",
        ],
    }

    # Compute headline gate status from the explicit recorded scopes.
    global_pass = all(x["pass"] for x in global_deltas.values())
    modal_pass = all(
        modal_deltas[scope][f"{field}_pass"]
        for scope in ("all_N96_keys_with_N64_zero_extension", "power_carrying_N96")
        for field in ("R", "T")
    )
    field_pass = all(v["pass"] for v in fields.values()) and boundary_all["pass"]
    result["comparison_gates"] = {
        "global_1e-5": global_pass,
        "all_signed_and_power_carrying_R_T_1e-6_with_explicit_zero_extension": modal_pass,
        "boundary_and_sampled_E_H_1e-4_no_phase_fit": field_pass,
        "finite_N64_to_N96_comparison_all_three_groups_pass": global_pass and modal_pass and field_pass,
        "does_not_imply_full_DTN_or_full_auto_inventory": True,
    }

    output = OUTCOMES / "records/d07c_g3_m8_n64_n96_saved_output_comparison_v1.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({
        "output": str(output),
        "output_sha256": sha256(output),
        "comparison_gates": result["comparison_gates"],
        "mode_counts": result["mode_counts"],
        "global_observables": result["global_observables"],
        "named_channel_observables": result["named_channel_observables"],
        "modal_R_T": {k: v for k, v in modal_deltas.items() if k in ("all_N96_keys_with_N64_zero_extension", "power_carrying_N96", "propagating_N96", "N96_added_keys")},
        "boundary": boundary_all,
        "sampled_complex_fields_overall": fields,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
