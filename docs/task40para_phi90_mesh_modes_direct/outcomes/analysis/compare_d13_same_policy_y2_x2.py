"""Offline same-policy D13 Y2/X2 comparison from saved terminal outputs."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import tomllib
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[4]
RESULTS = REPO / "results/si_block_phi90_50x50_17x20_h120"
OUT = REPO / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
JSON_OUT = OUT / "d13_y2_x2_same_policy_comparison_v1.json"
CSV_OUT = OUT / "d13_y2_x2_same_policy_all_612_modes_v1.csv"
MODE_SHA = "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
CASES = {
    "Y2": {
        "directory": "task40_phi90_13p5_D13_Y2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261016T190312.893443Z",
        "source_sha": "73e2fd2c4a36c9698298235148c59aa1551d74d6",
        "input_sha256": "7908141fe455ee73a1c8f213970a5c5655095a31f6afd10ce18904367b63a994",
        "axis_counts": [6, 24, 14],
    },
    "X2": {
        "directory": "task40_phi90_13p5_D13_X2_from_Y2_p6_direct_v1__full3d_direct__mpi1__Mna",
        "stamp": "20261016T230205.407937Z",
        "source_sha": "bfabcf8c1771e7f79ed89c184ff617c8edda8dca",
        "input_sha256": "90f05fe4eb151bd076b62400d072af03c170a9a34e8108af13721fd56f71dd15",
        "axis_counts": [12, 24, 14],
    },
}
SAMPLE_FIELDS = (
    "E_V_per_m",
    "H_A_per_m",
    "E_t_interface_V_per_m",
    "H_t_interface_A_per_m",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> tuple[Any, str]:
    data = path.read_bytes()
    return json.loads(data), _sha(data)


def _complex(pair: list[float] | tuple[float, float]) -> complex:
    return complex(float(pair[0]), float(pair[1]))


def _key(row: dict[str, Any]) -> tuple[str, str, int, int, str]:
    return (
        str(row["side"]), str(row["direction"]), int(row["m"]),
        int(row["n"]), str(row["polarization"]),
    )


def _array_sha(value: np.ndarray) -> str:
    return _sha(np.ascontiguousarray(value).view(np.uint8).tobytes())


def _norm_comparison(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    a = np.asarray(reference)
    b = np.asarray(candidate)
    delta = b - a
    norm_a = float(np.linalg.norm(a.ravel()))
    norm_b = float(np.linalg.norm(b.ravel()))
    norm_delta = float(np.linalg.norm(delta.ravel()))
    flat_index = int(np.argmax(np.abs(delta))) if delta.size else 0
    return {
        "reference_l2": norm_a,
        "candidate_l2": norm_b,
        "delta_l2": norm_delta,
        "relative_l2_to_Y2": norm_delta / norm_a if norm_a else None,
        "relative_l2_to_X2": norm_delta / norm_b if norm_b else None,
        "max_abs_delta": float(np.max(np.abs(delta), initial=0.0)),
        "max_delta_index": [
            int(i) for i in np.unravel_index(flat_index, delta.shape)
        ] if delta.size else [],
    }


def _load_case(label: str, spec: dict[str, Any]) -> dict[str, Any]:
    run = RESULTS / spec["directory"] / spec["stamp"]
    output = run / "numerical_output"
    summary, summary_sha = _read_json(run / "run_summary.json")
    manifest, manifest_sha = _read_json(run / "run_manifest.json")
    phase, phase_sha = _read_json(run / "workflow_phase.json")
    direct, direct_sha = _read_json(run / "p6_condensed_direct_summary.json")
    resolved, resolved_sha = _read_json(run / "resolved_config.json")
    power, power_sha = _read_json(output / "dtn_port_power_metrics_3d.json")
    volume, volume_sha = _read_json(output / "volume_absorption.json")
    modes, modes_sha = _read_json(output / "dtn_port_diffraction_orders_3d.json")
    auxiliary, auxiliary_sha = _read_json(output / "dtn_auxiliary_amplitudes_3d.json")
    sample_meta, sample_meta_sha = _read_json(output / "full3d_reference_samples.json")

    resource = summary["resource_authority"]
    if summary["result_classification"] != "worker_exit0" or summary["exit_status"] != 0:
        raise ValueError(f"{label}: run did not exit successfully")
    if not resource["descendants_cleared"] or resource["remaining_child_pids"]:
        raise ValueError(f"{label}: process tree was not cleared")
    if not direct["passed"] or not direct["complete_solve"]:
        raise ValueError(f"{label}: direct solve summary did not pass")
    if power["active_mode_count"] != 612 or power["active_mode_sha256"] != MODE_SHA:
        raise ValueError(f"{label}: active mode identity mismatch")
    if direct["mesh_evidence"]["axis_cell_counts"] != spec["axis_counts"]:
        raise ValueError(f"{label}: actual mesh counts mismatch")
    if direct["production_port_mpc_witness"]["dtn_quadrature_degree"] != 28:
        raise ValueError(f"{label}: surface quadrature mismatch")
    operator = direct["direct_factor_evidence"]["operator_identity"]
    if operator["dtn_sparse_cutoff_policy"] != "scale_homogeneous_relative_only_v1":
        raise ValueError(f"{label}: cutoff policy mismatch")
    if operator["dtn_sparse_cutoff_relative_tolerance"] != 1e-13:
        raise ValueError(f"{label}: cutoff tolerance mismatch")
    if operator["parent_mode_sha256"] != MODE_SHA:
        raise ValueError(f"{label}: operator mode manifest mismatch")

    source_sha = (run / "source_sha.txt").read_text().strip()
    input_sha = (run / "input_sha256.txt").read_text().strip()
    physical_sha = (run / "physical_model_sha256.txt").read_text().strip()
    if source_sha != spec["source_sha"] or manifest["source_sha"] != source_sha:
        raise ValueError(f"{label}: source identity mismatch")
    if input_sha != spec["input_sha256"] or manifest["input_sha256"] != input_sha:
        raise ValueError(f"{label}: input identity mismatch")
    if manifest.get("physical_model_sha256") != physical_sha:
        raise ValueError(f"{label}: physical identity mismatch")
    if len(modes["orders"]) != 612 or len(auxiliary) != 612:
        raise ValueError(f"{label}: incomplete modal records")
    if [int(row["auxiliary_index"]) for row in modes["orders"]] != list(range(612)):
        raise ValueError(f"{label}: modal rows are not in auxiliary-index order")
    if [int(row["auxiliary_index"]) for row in auxiliary] != list(range(612)):
        raise ValueError(f"{label}: auxiliary rows are not in auxiliary-index order")
    if any(_key(a) != _key(b) for a, b in zip(modes["orders"], auxiliary, strict=True)):
        raise ValueError(f"{label}: modal and auxiliary keys differ")

    npz_path = output / "full3d_reference_samples.npz"
    archive_bytes = npz_path.read_bytes()
    archive_sha = _sha(archive_bytes)
    if archive_sha != sample_meta["archive_sha256"]:
        raise ValueError(f"{label}: sample NPZ hash does not match metadata")
    if len(archive_bytes) != sample_meta["archive_bytes"]:
        raise ValueError(f"{label}: sample NPZ byte count mismatch")
    with np.load(io.BytesIO(archive_bytes), allow_pickle=False) as archive:
        samples = {name: archive[name].copy() for name in archive.files}
    if any(name not in samples for name in (*SAMPLE_FIELDS, "x_nm", "y_nm", "z_nm")):
        raise ValueError(f"{label}: sample archive is incomplete")

    return {
        "label": label,
        "run_directory": str(run),
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "resolved_config": resolved,
        "run_manifest_sha256": manifest_sha,
        "run_summary_sha256": summary_sha,
        "workflow_phase_sha256": phase_sha,
        "classification": summary["result_classification"],
        "exit_status": summary["exit_status"],
        "terminal_stage": phase.get("stage"),
        "qualification_status": direct["status"],
        "full_dtn_status": direct["full_dtn_status"],
        "mesh": {
            "axis_cell_counts": direct["mesh_evidence"]["axis_cell_counts"],
            "actual_global_cell_count": direct["mesh_evidence"]["actual_global_cell_count"],
            "axis_sha256_le_f64": direct["mesh_evidence"]["axis_sha256_le_f64"],
        },
        "mode_sha256": power["active_mode_sha256"],
        "mode_count": power["active_mode_count"],
        "surface_quadrature_degree": direct["production_port_mpc_witness"]["dtn_quadrature_degree"],
        "cutoff_identity_sha256": operator["dtn_sparse_cutoff_identity_sha256"],
        "volume_quadrature_records": direct["operator_identity"]["volume_quadrature_records"],
        "totals": {
            "R_total": power["R_total"],
            "R00_s": power["R00_s"],
            "R00_p": power["R00_p"],
            "R00_total": power["R00_total"],
            "T_total": power["T_total"],
            "A_balance": power["A_balance"],
            "A_volume": volume["A_volume_total"],
            "A_grating": volume["A_grating"],
            "A_substrate": volume["A_substrate"],
            "energy_closure_abs": abs(
                1.0 - power["R_total"] - power["T_total"] - volume["A_volume_total"]
            ),
        },
        "solver": {
            "condensed_relative": direct["residuals"]["condensed_direct_relative"],
            "original_A6_relative": direct["residuals"]["original_A6_active_rectangle_relative"],
            "same_factor_corrections": direct["factor"]["same_factor_correction_count"],
        },
        "resource": {
            "elapsed_seconds": resource["elapsed_seconds"],
            "tree_rss_peak_bytes": resource["sampled_process_tree_rss_peak_bytes"],
            "tree_swap_peak_bytes": resource["sampled_process_tree_swap_peak_bytes"],
            "runtime_min_available_bytes": "UNKNOWN_NOT_AGGREGATED",
            "host_available_floor_threshold_bytes": resource["minimum_available_bytes"],
            "launch_effective_available_bytes": resource["launch_envelope"].get("effective_available_bytes"),
            "launch_mem_available_bytes": resource["launch_envelope"].get("mem_available_bytes"),
            "job_swap_activity": resource["job_swap_activity"],
            "global_swap_activity": resource.get("global_swap_activity"),
        },
        "orders": modes["orders"],
        "auxiliary": auxiliary,
        "samples": samples,
        "sample_metadata": sample_meta,
        "artifact_hashes": {
            "direct_summary_sha256": direct_sha,
            "power_metrics_sha256": power_sha,
            "volume_absorption_sha256": volume_sha,
            "diffraction_orders_sha256": modes_sha,
            "auxiliary_sha256": auxiliary_sha,
            "sample_metadata_sha256": sample_meta_sha,
            "sample_npz_sha256": archive_sha,
        },
    }


def _compare_modes(y2: dict[str, Any], x2: dict[str, Any]) -> dict[str, Any]:
    arows, brows = y2["orders"], x2["orders"]
    keys_a, keys_b = [_key(row) for row in arows], [_key(row) for row in brows]
    if keys_a != keys_b:
        raise ValueError("Y2/X2 mode ordering differs")
    for idx, (a, b) in enumerate(zip(arows, brows, strict=True)):
        for field in ("medium", "beta", "boundary_phase", "propagating", "power_carrying", "refractive_index"):
            if a[field] != b[field]:
                raise ValueError(f"mode physical identity differs at {idx}: {field}")

    complex_fields = (
        "outgoing_amplitude_at_boundary",
        "outgoing_amplitude",
        "auxiliary_amplitude_total_projection",
    )
    amplitude_metrics = {}
    for field in complex_fields:
        va = np.asarray([_complex(row[field]) for row in arows], dtype=np.complex128)
        vb = np.asarray([_complex(row[field]) for row in brows], dtype=np.complex128)
        delta = vb - va
        order = np.argsort(np.abs(delta))[::-1]
        amplitude_metrics[field] = {
            **_norm_comparison(va, vb),
            "max_delta_key": list(keys_a[int(order[0])]),
            "top_10_abs_delta": [
                {"key": list(keys_a[int(i)]), "abs_delta": float(abs(delta[int(i)]))}
                for i in order[:10]
            ],
        }

    classes = {
        "all_612": np.ones(612, dtype=bool),
        "propagating": np.asarray([bool(row["propagating"]) for row in arows]),
        "power_carrying": np.asarray([bool(row["power_carrying"]) for row in arows]),
        "evanescent_nonpropagating": np.asarray([not bool(row["propagating"]) for row in arows]),
        "non_power_carrying": np.asarray([not bool(row["power_carrying"]) for row in arows]),
    }
    power_metrics = {}
    for class_name, mask in classes.items():
        indices = np.flatnonzero(mask)
        power_metrics[class_name] = {"count": int(indices.size)}
        for field in ("R", "T", "modal_power_code_units", "power_ratio"):
            va = np.asarray([float(arows[int(i)][field]) for i in indices])
            vb = np.asarray([float(brows[int(i)][field]) for i in indices])
            delta = vb - va
            local = int(np.argmax(np.abs(delta))) if delta.size else 0
            power_metrics[class_name][field] = {
                "delta_l2": float(np.linalg.norm(delta)),
                "max_abs_delta": float(np.max(np.abs(delta), initial=0.0)),
                "max_delta_key": list(keys_a[int(indices[local])]) if delta.size else None,
            }
    return {
        "all_612_key_order_and_branch_identity_exact": True,
        "complex_amplitudes": amplitude_metrics,
        "per_mode_power_differences": power_metrics,
    }


def _write_csv(y2: dict[str, Any], x2: dict[str, Any]) -> str:
    fields = [
        "auxiliary_index", "side", "direction", "m", "n", "polarization",
        "propagating", "power_carrying", "beta_re", "beta_im",
        "Y2_boundary_re", "Y2_boundary_im", "X2_boundary_re", "X2_boundary_im",
        "delta_boundary_abs", "Y2_raw_outgoing_re", "Y2_raw_outgoing_im",
        "X2_raw_outgoing_re", "X2_raw_outgoing_im", "Y2_total_projection_re",
        "Y2_total_projection_im", "X2_total_projection_re", "X2_total_projection_im",
        "Y2_R", "X2_R", "delta_R", "Y2_T", "X2_T", "delta_T",
        "Y2_modal_power_code_units", "X2_modal_power_code_units", "delta_modal_power_code_units",
        "Y2_power_ratio", "X2_power_ratio", "delta_power_ratio",
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for a, b in zip(y2["orders"], x2["orders"], strict=True):
            row = {
                "auxiliary_index": a["auxiliary_index"], "side": a["side"],
                "direction": a["direction"], "m": a["m"], "n": a["n"],
                "polarization": a["polarization"], "propagating": a["propagating"],
                "power_carrying": a["power_carrying"],
                "beta_re": a["beta"][0], "beta_im": a["beta"][1],
            }
            for label, item in (("Y2", a), ("X2", b)):
                for prefix, key in (
                    ("boundary", "outgoing_amplitude_at_boundary"),
                    ("raw_outgoing", "outgoing_amplitude"),
                    ("total_projection", "auxiliary_amplitude_total_projection"),
                ):
                    z = _complex(item[key])
                    row[f"{label}_{prefix}_re"] = z.real
                    row[f"{label}_{prefix}_im"] = z.imag
                for metric in ("R", "T", "modal_power_code_units", "power_ratio"):
                    row[f"{label}_{metric}"] = item[metric]
            zb = _complex(b["outgoing_amplitude_at_boundary"]) - _complex(a["outgoing_amplitude_at_boundary"])
            row["delta_boundary_abs"] = abs(zb)
            for metric in ("R", "T", "modal_power_code_units", "power_ratio"):
                row[f"delta_{metric}"] = float(b[metric]) - float(a[metric])
            writer.writerow(row)
    return _sha(CSV_OUT.read_bytes())


def _global_observables(y2: dict[str, Any], x2: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for field in y2["totals"]:
        a, b = float(y2["totals"][field]), float(x2["totals"][field])
        result[field] = {"Y2": a, "X2": b, "delta_X2_minus_Y2": b - a, "absolute_delta": abs(b - a)}
    return result


def _resolved_diff_paths(a: Any, b: Any, prefix: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        paths = []
        for key in sorted(set(a) | set(b)):
            child = f"{prefix}.{key}" if prefix else key
            if key not in a or key not in b:
                paths.append(child)
            else:
                paths.extend(_resolved_diff_paths(a[key], b[key], child))
        return paths
    return [] if a == b else [prefix]


def _main() -> None:
    cases = {
        name: _load_case(name, spec)
        for name, spec in CASES.items()
    }
    y2, x2 = cases["Y2"], cases["X2"]
    same_coords = all(
        np.array_equal(y2["samples"][name], x2["samples"][name])
        for name in ("x_nm", "y_nm", "z_nm")
    )
    if not same_coords:
        raise ValueError("saved field sample coordinates differ; no interpolation allowed")
    sample_metrics = {}
    for field in SAMPLE_FIELDS:
        a, b = y2["samples"][field], x2["samples"][field]
        item = {"shape": list(a.shape), "dtype": str(a.dtype), **_norm_comparison(a, b)}
        if a.ndim and a.shape[-1] == 3:
            item["per_component"] = [
                {"component": c, **_norm_comparison(a[..., i], b[..., i])}
                for i, c in enumerate(("x", "y", "z"))
            ]
        sample_metrics[field] = item

    modal = _compare_modes(y2, x2)
    csv_sha = _write_csv(y2, x2)
    sample_coords = {
        name: {
            "shape": list(y2["samples"][name].shape),
            "dtype": str(y2["samples"][name].dtype),
            "sha256": _array_sha(y2["samples"][name]),
        }
        for name in ("x_nm", "y_nm", "z_nm")
    }

    dats = {}
    for label, spec in CASES.items():
        path = RESULTS.parents[1] / "input/task40para_phi90_mesh_modes_direct" / (
            "d13_y2_r13_p6_direct.dat" if label == "Y2" else "d13_x2_from_y2_r13_p6_direct.dat"
        )
        dats[label] = tomllib.loads(path.read_text())
    common_sections = ("geometry", "materials", "incidence", "boundary", "method", "execution", "output")
    common_contract_exact = all(dats["Y2"][key] == dats["X2"][key] for key in common_sections)
    if not common_contract_exact:
        raise ValueError("non-mesh input contract differs between Y2 and X2")
    if dats["Y2"]["discretization"]["nedelec_degree"] != dats["X2"]["discretization"]["nedelec_degree"]:
        raise ValueError("polynomial degree differs")

    resolved_diffs = _resolved_diff_paths(y2["resolved_config"], x2["resolved_config"])
    allowed_prefixes = (
        "derived.mesh_cells", "derived.native_capacity_profile",
        "discretization.mesh_axis_cell_counts", "discretization.mesh_axis_x_values",
        "discretization.mesh_plan_id", "discretization.mesh_plan_sha256",
        "provenance.expected_output_parent", "provenance.input_sha256",
        "provenance.physical_model_sha256", "provenance.source_path",
        "run_id", "solver.native_capacity_profile",
    )
    unexpected = [
        p for p in resolved_diffs
        if not any(p == q or p.startswith(q + ".") for q in allowed_prefixes)
    ]
    if unexpected:
        raise ValueError(f"unexpected resolved differences: {unexpected}")
    mh_y, mh_x = y2["mesh"]["axis_sha256_le_f64"], x2["mesh"]["axis_sha256_le_f64"]
    if mh_y["y"] != mh_x["y"] or mh_y["z"] != mh_x["z"] or mh_y["x"] == mh_x["x"]:
        raise ValueError("actual mesh evidence is not an x-only change")
    if y2["volume_quadrature_records"] != x2["volume_quadrature_records"]:
        raise ValueError("volume integration records differ")
    if y2["cutoff_identity_sha256"] != x2["cutoff_identity_sha256"]:
        raise ValueError("relative-only cutoff identity differs")

    report = {
        "schema": "task40.d13.same_relative_only_y2_x2_saved_output_comparison.v1",
        "scope": "offline comparison of terminal same-policy Y2 and X2 outputs; no FE, factor, VTU, or resource-stream read",
        "interpretation": "one-axis x refinement under the finite active R13 operator; finite-R13 evidence only, not full-DtN or continuum qualification",
        "same_numerical_policy": {
            "p6_degree": 6,
            "active_mode_count": 612,
            "active_mode_sha256": MODE_SHA,
            "surface_quadrature_degree": 28,
            "volume_quadrature_records_equal": True,
            "sparse_cutoff_policy": "scale_homogeneous_relative_only_v1",
            "sparse_cutoff_tolerance": 1e-13,
            "sparse_cutoff_identity_sha256": y2["cutoff_identity_sha256"],
            "common_input_physics_sections_exact": common_contract_exact,
            "resolved_config_diff_paths": resolved_diffs,
            "source_sha_equal": y2["source_sha"] == x2["source_sha"],
            "source_sha": {k: cases[k]["source_sha"] for k in cases},
            "source_change_note": "Y2 source 73e2fd2 and X2 source bfabcf8 differ. The intervening production diff is limited to D13 X2 axis/profile/mesh-evidence plumbing; the p6 condensation/assembly, DtN action, and physical operator implementation did not change.",
        },
        "mesh": {
            "Y2": y2["mesh"],
            "X2": x2["mesh"],
            "only_x_axis_changed": True,
            "x_sha256_changed": True,
            "y_sha256_identical": True,
            "z_sha256_identical": True,
        },
        "global_observable_comparison": _global_observables(y2, x2),
        "modal_comparison": modal,
        "same_coordinate_complex_field_comparison": sample_metrics,
        "sample_coordinates": {"exactly_equal": True, "axes": sample_coords, "metadata": y2["sample_metadata"]},
        "cases": {
            name: {
                key: value for key, value in case.items()
                if key not in ("orders", "auxiliary", "samples", "resolved_config")
            }
            for name, case in cases.items()
        },
        "scope_limits": [
            "All 612 active modal rows are compared; this does not test omitted modes or verify full DtN.",
            "Saved field arrays are finite common samples only, not full-domain L2 norms.",
            "Saved tangential fields are on horizontal z planes, not canonical pillar sidewalls.",
            "No interpolation, global phase fit, or field reconstruction was performed.",
            "Y2 and X2 source SHAs differ; exact-source identity is not claimed, though the reviewed intervening source changes are limited to X2 mesh/profile/evidence plumbing.",
        ],
        "csv": {"path": str(CSV_OUT.relative_to(REPO)), "rows": 612, "sha256": csv_sha},
        "analysis_script": {"path": str(Path(__file__).resolve().relative_to(REPO)), "sha256": _sha(Path(__file__).read_bytes())},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"json": str(JSON_OUT), "json_sha256": _sha(JSON_OUT.read_bytes()), "csv": str(CSV_OUT), "csv_sha256": csv_sha, "all_modes": 612}, sort_keys=True))


if __name__ == "__main__":
    _main()
