#!/usr/bin/env python3
"""Offline all-mode and saved-field comparisons for completed D15 X2/Z3-3.

Reads only each run's small manifest/summary/stage JSON, resolved config,
modal/power/volume JSON, and the 1.3 MB saved reference-sample NPZ. It never
opens VTU or resource streams and performs no mesh, FE, factor, or solve work.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
MODEL = "si_block_phi90_50x50_17x20_h120"
RESULTS = ROOT / "results" / MODEL
RECORDS = ROOT / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
RUNS = {
    "D15-B": "task40_phi90_13p5_D15_B_p6_direct_v1__full3d_direct__mpi1__Mna/20261021T063110.066502Z",
    "D15-X2": "task40_phi90_13p5_D15_X2_p6_direct_v1__full3d_direct__mpi1__Mna/20261022T144146.393090Z",
    "D15-Z3-3": "task40_phi90_13p5_D15_Z3_3_p6_direct_v1__full3d_direct__mpi1__Mna/20261022T115025.174499Z",
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
    "D15-X2": {
        "run_id": "task40_phi90_13p5_D15_X2_p6_direct_v1",
        "source_sha": "405e3aff42ac421a4c99315df1ed9b96941ecbe4",
        "input_sha256": "8334730a14e264246f44bd274c890ba11fbf504c20c2c825bd97fb9d91433548",
        "physical_model_sha256": "4a711a4c3fbdb52fe8109cf6f2b1a0dabbe8d421fb441c846766b668b0bd1a76",
        "resolved_config_sha256": "7cfa96b1a056eed343213d3df31d8cd9ed89c04c49b51ed30d54d3fcd58a27ff",
        "axis_counts": [10, 4, 6],
        "axis_sha256": {
            "x": "5aeca229192ae6c745a47a29c937ea6326fbed913a51a778727e28e7d04e0609",
            "y": "c0a1052034574ddda40b805390f8debb6abd3da6ec558cc0458820ee941198ba",
            "z": "daf722948a31d19757622ba67544eeea6d49fdc2e433b979df9c11b2b450afb6",
        },
    },
    "D15-Z3-3": {
        "run_id": "task40_phi90_13p5_D15_Z3_3_p6_direct_v1",
        "source_sha": "405e3aff42ac421a4c99315df1ed9b96941ecbe4",
        "input_sha256": "9e9c4f4c1631f73abbee9de4133cd77dbcc4df4477c278a414d6f8211ebd9e98",
        "physical_model_sha256": "203543273f080aa318920cfc8c30c47e33414b0e11308cb93957a06209e9ed75",
        "resolved_config_sha256": "eb152e58ab78243cbf5c7a6cb7ff2b04f8be0f3810ba7e1831e63dbc551d7ea3",
        "axis_counts": [6, 4, 12],
        "axis_sha256": {
            "x": "bb1d6be1e2cec153c7bd67a71e29f5967b3035b4928cd06f51ee2c0b6f2a5361",
            "y": "c0a1052034574ddda40b805390f8debb6abd3da6ec558cc0458820ee941198ba",
            "z": "ff7bdf40fb227a07452cfe9bed26279e7f671164353131e03c8833b9f1281c12",
        },
    },
}
MODE_SHA = "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
PAIRS = (("D15-B", "D15-X2"), ("D15-B", "D15-Z3-3"))


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _axis_sha(values: list[float]) -> str:
    import numpy as np

    return hashlib.sha256(np.ascontiguousarray(np.asarray(values, dtype="<f8")).tobytes()).hexdigest()


def _load_d15_helper() -> Any:
    path = Path(__file__).with_name("compare_d15_b_z1_z2_same_contract.py")
    spec = importlib.util.spec_from_file_location("task40_d15_saved_compare", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load saved-output comparison helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RESULTS = RESULTS
    module.RUNS = RUNS
    module.EXPECTED = EXPECTED
    return module


def _identity(label: str, case: dict[str, Any]) -> dict[str, Any]:
    run = case["run"]
    manifest = case["manifest"]
    resolved_bytes = (run / "resolved_config.json").read_bytes()
    resolved = json.loads(resolved_bytes)
    actual = {
        "run_id": manifest.get("run_id"),
        "source_sha": manifest.get("source_sha"),
        "input_sha256": manifest.get("input_sha256"),
        "physical_model_sha256": manifest.get("physical_model_sha256"),
        "resolved_config_sha256": manifest.get("resolved_config_sha256"),
    }
    expected = EXPECTED[label]
    for key, value in expected.items():
        if key in actual and actual[key] != value:
            raise ValueError(f"{label}: {key} identity mismatch")
    if _sha(run / "input_original.dat") != actual["input_sha256"]:
        raise ValueError(f"{label}: saved input hash mismatch")
    if hashlib.sha256(resolved_bytes).hexdigest() != actual["resolved_config_sha256"]:
        raise ValueError(f"{label}: resolved config hash mismatch")
    if (run / "physical_model_sha256.txt").read_text().strip() != actual["physical_model_sha256"]:
        raise ValueError(f"{label}: physical identity file mismatch")
    if (run / "source_sha.txt").read_text().strip() != actual["source_sha"]:
        raise ValueError(f"{label}: source identity file mismatch")

    discretization = resolved["discretization"]
    axes = {
        axis: [float(item) for item in discretization[f"mesh_axis_{axis}_values"]]
        for axis in ("x", "y", "z")
    }
    hashes = {axis: _axis_sha(values) for axis, values in axes.items()}
    actual_counts = [len(axes[axis]) - 1 for axis in ("x", "y", "z")]
    if actual_counts != expected["axis_counts"] or hashes != expected["axis_sha256"]:
        raise ValueError(f"{label}: resolved axis identity mismatch")
    qa = case["mesh_qa"]
    if qa.get("axis_cell_counts") != actual_counts or qa.get("axis_sha256_le_f64") != hashes:
        raise ValueError(f"{label}: actual mesh QA differs from resolved axes")

    surface = case["surface_contract"]
    volumes = surface.get("volume_quadrature_records") or []
    if (
        surface.get("degree") != 6
        or surface.get("active_mode_count") != 612
        or surface.get("active_mode_sha256") != MODE_SHA
        or surface.get("parent_quadrature_degree") != 28
        or surface.get("dtn_sparse_cutoff_policy") != "scale_homogeneous_relative_only_v1"
        or surface.get("dtn_sparse_cutoff_relative_tolerance") != 1e-13
        or not volumes
        or any(v.get("quadrature_degree") != 15 or v.get("quadrature_rule") != "default" for v in volumes)
    ):
        raise ValueError(f"{label}: solver/mode/quadrature/cutoff identity mismatch")
    if case["power"].get("active_mode_count") != 612 or case["power"].get("active_mode_sha256") != MODE_SHA:
        raise ValueError(f"{label}: power output modal identity mismatch")

    sections = {key: resolved[key] for key in ("geometry", "materials", "incidence", "boundary")}
    return {
        "run_directory": str(run.relative_to(ROOT)),
        **actual,
        "execution_mode": manifest.get("execution_mode"),
        "profile": manifest.get("native_capacity_profile_identity"),
        "axis_cell_counts": actual_counts,
        "resolved_axes_nm": axes,
        "axis_sha256_le_f64": hashes,
        "actual_mesh_qa": qa,
        "mode_count": 612,
        "mode_sha256": MODE_SHA,
        "surface_q": 28,
        "volume_quadrature_records": volumes,
        "cutoff_policy": surface.get("dtn_sparse_cutoff_policy"),
        "cutoff_relative_tolerance": surface.get("dtn_sparse_cutoff_relative_tolerance"),
        "terminal": {
            "phase": case["phase"].get("phase"),
            "passed": case["phase"].get("facts", {}).get("passed"),
            "status": case["summary"].get("status"),
            "exit_status": case["summary"].get("exit_status"),
            "descendants_cleared": case["authority"].get("descendants_cleared"),
        },
        "sample_archive_sha256": case["sample_meta"].get("archive_sha256"),
        "sample_arrays_shape": case["sample_meta"].get("array_shape_z_y_x_component"),
        "global_values": {
            key: case["power"].get(key)
            for key in ("R_total", "T_total", "A_balance", "R00_s", "R00_total")
        } | {"A_volume_total": case["volume"].get("A_volume_total")},
        "runtime_small_summary": {
            "elapsed_seconds": case["authority"].get("elapsed_seconds"),
            "tree_rss_peak_bytes": case["authority"].get("sampled_process_tree_rss_peak_bytes"),
            "tree_swap_peak_bytes": case["authority"].get("sampled_process_tree_swap_peak_bytes"),
        },
        "_sections": sections,
        "_axes": axes,
    }


def main() -> None:
    helper_module = _load_d15_helper()
    helper = helper_module._load_helper()
    cases = {label: helper._read_case(label) for label in RUNS}
    identities = {label: _identity(label, case) for label, case in cases.items()}
    base = identities["D15-B"]
    if any(identities[label]["_sections"] != base["_sections"] for label in RUNS if label != "D15-B"):
        raise ValueError("saved geometry/material/incidence/boundary identities differ")
    for label, changed_axis in (("D15-X2", "x"), ("D15-Z3-3", "z")):
        for axis in ("x", "y", "z"):
            different = identities[label]["_axes"][axis] != base["_axes"][axis]
            if different != (axis == changed_axis):
                raise ValueError(f"{label}: expected only {changed_axis} to differ from D15-B")
    if len({identities[label]["source_sha"] for label in RUNS}) == 1:
        source_relation = "same source SHA"
    else:
        source_relation = "source SHA differs; actual physics/mode/q/cutoff/mesh identities checked separately"

    output_json = RECORDS / "d15_x2_z3_3_saved_output_comparison_20261023_v1.json"
    output_csv = RECORDS / "d15_x2_z3_3_all_612_modes_20261023_v1.csv"
    output_md = ROOT / "docs/task40para_phi90_mesh_modes_direct/outcomes/response_d15_x2_z3_3_offline_comparison_20261023.md"
    columns = [
        "reference_case", "candidate_case", "side", "m", "n", "polarization", "propagating", "power_carrying",
        "reference_R", "candidate_R", "delta_R", "reference_T", "candidate_T", "delta_T",
        "reference_boundary_re", "reference_boundary_im", "candidate_boundary_re", "candidate_boundary_im",
        "boundary_delta_abs", "boundary_delta_rel_to_reference_mode",
        "reference_raw_outgoing_re", "reference_raw_outgoing_im", "candidate_raw_outgoing_re", "candidate_raw_outgoing_im",
    ]
    comparisons: dict[str, Any] = {}
    RECORDS.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for reference_label, candidate_label in PAIRS:
            pair = helper_module._compare_pair(
                helper, reference_label, candidate_label,
                cases[reference_label], cases[candidate_label], writer,
            )
            comparisons[f"{reference_label}_vs_{candidate_label}"] = pair
    for identity in identities.values():
        identity.pop("_sections")
        identity.pop("_axes")
    payload = {
        "schema": "task40.d15_x2_z3_3_offline_saved_output_comparison.v1",
        "created_from": "offline small saved outputs; no FE, factor, solve, VTU, or resource-stream read",
        "analysis_source_script": {"path": str(Path(__file__).relative_to(ROOT)), "sha256": _sha(Path(__file__))},
        "source_relation": source_relation,
        "between_source_change_review": {
            "baseline_source_sha": EXPECTED["D15-B"]["source_sha"],
            "variant_source_sha": EXPECTED["D15-X2"]["source_sha"],
            "changed_runtime_files": {
                "src/io/native_capacity_profile.py": "adds later D15 case/profile metadata and display identity",
                "src/runners/p6_condensed_direct.py": "extends frozen mesh-evidence lineage/hash reporting for later D15 cases",
                "src/runners/native_capacity.py": "passes run identity into host admission",
                "src/runners/reviewed_workstation_admission.py": "adds the reviewed Task41 parallel-admission exception",
            },
            "numerical_operator_or_solver_algorithm_change_in_these_runtime_diffs": False,
            "basis": "direct source diff between the two recorded source commits; mode, quadrature, cutoff, physical sections, and each live mesh identity are also checked from the saved run evidence",
        },
        "case_identities": identities,
        "operator_contract": {
            "p6_direct_full_solve": True,
            "active_rectangle_only": True,
            "mode_count": 612,
            "mode_sha256": MODE_SHA,
            "surface_q": 28,
            "volume_q_records": "q15/default, exact records in each case identity",
            "cutoff_policy": "scale_homogeneous_relative_only_v1",
            "cutoff_relative_tolerance": 1e-13,
            "full_dtn": "FULL_DTN_NOT_VERIFIED",
        },
        "mesh_lineage": {
            "D15-B_to_D15-X2": "x-only refinement; y/z resolved coordinate arrays and hashes are identical",
            "D15-B_to_D15-Z3-3": "z-only refinement; x/y resolved coordinate arrays and hashes are identical",
            "cross_mesh_FE_or_factor_reuse": False,
        },
        "thresholds": helper_module.THRESHOLDS,
        "comparisons": comparisons,
        "scope_limits": [
            "Each pair compares one axis against D15-B; no inference is made about untested axis combinations.",
            "R/T/A and all 612 signed channel outputs are compared; power-carrying channels are reported separately and included in qualification.",
            "Complex boundary amplitudes and saved complex E/H use direct common coordinates, with no interpolation or phase fit.",
            "Saved horizontal Et/Ht are diagnostics only; canonical pillar sidewall traces remain NOT_MEASURED.",
            "A finite R5 active rectangle does not establish full DtN convergence.",
        ],
        "outputs": {
            "all_612_mode_csv": {"path": str(output_csv.relative_to(ROOT)), "sha256": _sha(output_csv), "rows": 2 * 612},
        },
    }
    payload["json_sha256_note"] = "SHA256 is recorded in the execution receipt after serialization; it is not self-hashed."
    output_json.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")

    def pair_line(key: str) -> str:
        pair = comparisons[key]
        global_values = pair["global_observables"]
        channels = pair["channel_groups"]["all_612"]
        power = pair["channel_groups"]["power_carrying"]
        fields = pair["same_coordinate_complex_E_H"]
        return (
            f"- **{key} — {pair['pair_gate']}**: "
            f"max all-612 |ΔR|={channels['R']['max_abs_delta']:.6g} "
            f"({channels['R']['key']}), |ΔT|={channels['T']['max_abs_delta']:.6g} "
            f"({channels['T']['key']}); power-carrying max |ΔR|={power['R']['max_abs_delta']:.6g}, "
            f"|ΔT|={power['T']['max_abs_delta']:.6g}; "
            f"ΔRtotal={global_values['R_total']['delta_candidate_minus_reference']:.6g}, "
            f"ΔTtotal={global_values['T_total']['delta_candidate_minus_reference']:.6g}, "
            f"ΔAvol={global_values['A_volume_total']['delta_candidate_minus_reference']:.6g}; "
            f"Erel={fields['E_V_per_m']['relative_l2_to_reference']:.6g}, "
            f"Hrel={fields['H_A_per_m']['relative_l2_to_reference']:.6g}."
        )

    output_md.write_text(
        "# D15 X2 and Z3-3 offline comparison\n\n"
        "This comparison uses only the completed D15-B, D15-X2, and D15-Z3-3 small outputs. "
        "No FE, factorization, solve, VTU, or resource-stream read was performed.\n\n"
        f"Source identities: {source_relation}. D15-B to X2 changes only x; D15-B to Z3-3 changes only z. "
        "All pairs retain p6 direct, the same 612-mode R5 active rectangle, surface q28, volume q15/default, "
        "and relative-only cutoff 1e-13.\n\n"
        "## Results\n\n"
        + pair_line("D15-B_vs_D15-X2") + "\n"
        + pair_line("D15-B_vs_D15-Z3-3") + "\n\n"
        "## Interpretation limits\n\n"
        "The comparison applies the original three gates: global R/T/A_balance/A_volume absolute difference "
        "<=1e-5; each of all 612 signed channel R/T values, including power-carrying channels, <=1e-6; "
        "boundary complex amplitude and same-coordinate complex E/H relative L2 <=1e-4 without phase fitting. "
        "The CSV contains all 1,224 pair-channel rows. Horizontal Et/Ht remain diagnostic; canonical pillar "
        "sidewalls are NOT_MEASURED. The finite R5 active rectangle does not establish full DtN convergence.\n\n"
        f"Machine-readable result: `{output_json.relative_to(ROOT)}` (SHA256 `{_sha(output_json)}`).\n"
        f"Per-channel data: `{output_csv.relative_to(ROOT)}` (SHA256 `{_sha(output_csv)}`).\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "json": str(output_json.relative_to(ROOT)), "json_sha256": _sha(output_json),
        "csv": str(output_csv.relative_to(ROOT)), "csv_sha256": _sha(output_csv),
        "markdown": str(output_md.relative_to(ROOT)), "markdown_sha256": _sha(output_md),
        "pair_gates": {key: value["pair_gate"] for key, value in comparisons.items()},
        "rows": 2 * 612,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
