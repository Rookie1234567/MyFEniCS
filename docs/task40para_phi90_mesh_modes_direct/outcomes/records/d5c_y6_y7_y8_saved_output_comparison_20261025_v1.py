"""Offline comparison of the completed D5C Y6/Y7/Y8 saved outputs.

Reads compact modal JSON and same-coordinate field-sample NPZ files only.
It does not read VTU, construct FE objects, or run a solve.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


W = Path("/home/fenics/Projects/Maxwell3D-Phi90")
OUT = W / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
BASE = W / "results/si_block_phi90_50x50_17x20_h120"
RUNS = {
    "D5C-Y6": BASE / "task40para_phi90_5_D5C_Y6_p6_direct_v1__full3d_direct__mpi1__Mna/20261024T021320.925991Z",
    "D5C-Y7": BASE / "task40para_phi90_5_D5C_Y7_p6_direct_v1__full3d_direct__mpi1__Mna/20261024T061944.262318Z",
    "D5C-Y8": BASE / "task40para_phi90_5_D5C_Y8_p6_direct_v1__full3d_direct__mpi1__Mna/20261024T154550.076339Z",
}
MODE_SHA = "752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc"
Y6_SOURCE = "1207cb78889fba6de4fd03ea72a238b334aa61a7"
Y8_SOURCE = "05bcfb5178ce3b90073f02fe03ef3279c2ca41b1"
P_GLOBAL, P_MODE, P_FIELD = 1e-5, 1e-6, 1e-4
PAIRS = [("D5C-Y6", "D5C-Y8"), ("D5C-Y7", "D5C-Y8")]
BASE_COMPARATOR = OUT / "d5c_y5_y6_y7_saved_output_comparison_20261024_v1.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    spec = importlib.util.spec_from_file_location("d5c_base_comparator", BASE_COMPARATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import existing comparator: {BASE_COMPARATOR}")
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)

    cases = {name: base.load_case(name, path) for name, path in RUNS.items()}
    reference_physical = cases["D5C-Y6"]["physical"]
    reference_op = cases["D5C-Y6"]["evidence"]["operator_identity"]
    for name, case in cases.items():
        if case["physical"] != reference_physical:
            raise ValueError(f"physical identity mismatch: {name}")
        op = case["evidence"]["operator_identity"]
        for key in (
            "active_mode_sha256", "active_mode_count", "degree",
            "dtn_sparse_cutoff_policy", "dtn_sparse_cutoff_relative_tolerance",
            "dtn_sparse_cutoff_identity_sha256", "parent_quadrature_degree",
            "volume_quadrature_records", "functional_store",
        ):
            if op[key] != reference_op[key]:
                raise ValueError(f"operator identity mismatch for {name}: {key}")
        if op["active_mode_count"] != 3772 or op["active_mode_sha256"] != MODE_SHA:
            raise ValueError(f"unexpected finite R5 mode inventory: {name}")
        if op["parent_quadrature_degree"] != 39:
            raise ValueError(f"unexpected surface quadrature: {name}")
        if any(
            rec["quadrature_degree"] != 15 or rec["quadrature_rule"] != "default"
            for rec in op["volume_quadrature_records"]
        ):
            raise ValueError(f"unexpected volume quadrature: {name}")

    source_diff = subprocess.run(
        ["git", "diff", "--name-status", f"{Y6_SOURCE}..{Y8_SOURCE}", "--", "src"],
        cwd=W, check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    if source_diff:
        raise ValueError(f"source revisions differ under src/: {source_diff}")

    comparisons = [base.compare(cases[a], cases[b]) for a, b in PAIRS]
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "d5c_y6_y7_y8_all_3772_modes_20261025_v1.csv"
    base.write_mode_csv(cases, PAIRS, csv_path)
    payload = {
        "schema": "task40.d5c.y6_y7_y8_saved_output_comparison.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": "offline compact modal JSON and same-coordinate saved field-sample NPZ only; no FE, factor, VTU, or resource-stream reads",
        "source_provenance": {
            "Y6_Y7_source_sha": Y6_SOURCE,
            "Y8_source_sha": Y8_SOURCE,
            "src_tree_diff": source_diff,
            "numerical_source_identity": "no src/ file differs between the recorded clean source revisions",
            "profile_and_input_identity": "case-specific input/resolved identities are recorded per run; physical fields and live operator identities are checked equal",
        },
        "identities": {name: case["identity"] for name, case in cases.items()},
        "thresholds": {
            "global_R_T_A_balance_A_volume_abs": P_GLOBAL,
            "each_channel_R_T_abs_all_3772_and_power_carrying": P_MODE,
            "R00_s_R00_total_abs": P_MODE,
            "boundary_complex_amplitude_relative_l2_no_phase_fit": P_FIELD,
            "same_coordinate_complex_E_H_relative_l2_no_phase_fit": P_FIELD,
        },
        "method": "Exact join by (side,m,n,polarization), no missing-key zero extension because all three inventories are the same 3772-key R5 set. All-mode, power-carrying, and propagating subsets are separately reported; all-mode and power-carrying groups gate. Boundary amplitudes and complex E/H use exact common saved sample coordinates, with no interpolation or phase fitting.",
        "grid_scope": {
            "D5C-Y6": {"axis_cell_counts": [6, 30, 6], "y_segments": [12, 6, 12], "independent_parent": "D5C-B"},
            "D5C-Y7": {"axis_cell_counts": [6, 30, 6], "y_segments": [10, 10, 10], "independent_parent": "D5C-B"},
            "D5C-Y8": {"axis_cell_counts": [6, 34, 6], "y_segments": [12, 10, 12], "independent_parent": "D5C-B"},
            "comparisons": {
                "D5C-Y6_to_Y8": "independent B-derived y allocations 12/6/12 to 12/10/12; x/z fixed to B",
                "D5C-Y7_to_Y8": "independent B-derived y allocations 10/10/10 to 12/10/12; x/z fixed to B",
            },
        },
        "limitations": ["AUTHORITY_LIMITED", "FULL_DTN_NOT_VERIFIED", "canonical_sidewall_NOT_MEASURED", "horizontal Et/Ht are diagnostics only", "Y6/Y7/Y8 comparisons assess only the recorded finite R5 inventory"],
        "mode_csv": {"path": str(csv_path), "sha256": sha(csv_path), "bytes": csv_path.stat().st_size, "rows_expected": 3772 * len(PAIRS)},
        "base_comparator_script_sha256": sha(BASE_COMPARATOR),
        "comparison_script_sha256": sha(Path(__file__)),
        "comparisons": comparisons,
    }
    json_path = OUT / "d5c_y6_y7_y8_saved_output_comparison_20261025_v1.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    summary = {
        "json": str(json_path),
        "json_sha256": sha(json_path),
        "csv": str(csv_path),
        "csv_sha256": sha(csv_path),
        "comparison_script_sha256": sha(Path(__file__)),
        "pairs": [
            {
                "reference": comp["reference"],
                "candidate": comp["candidate"],
                "global": comp["gate_groups"]["global_R_T_A_balance_A_volume"],
                "modes": comp["gate_groups"]["all_3772_and_power_carrying_mode_R_T_including_R00_s"],
                "fields": comp["gate_groups"]["boundary_and_same_coordinate_E_H"],
                "all_three": comp["all_three_gate_groups_pass"],
                "global_abs": {k: v["abs_delta"] for k, v in comp["global_observables"].items()},
                "all_3772_max_abs_R_T": {k: v["max_abs_delta"] for k, v in comp["per_mode_R_T"]["all_3772"].items()},
                "power_carrying_max_abs_R_T": {k: v["max_abs_delta"] for k, v in comp["per_mode_R_T"]["power_carrying"].items()},
                "boundary_relative": comp["boundary_complex_amplitude"]["relative_l2_no_phase_fit"],
                "E_H_relative": {k: v["relative_l2_no_phase_fit"] for k, v in comp["same_coordinate_fields"]["E_H"].items()},
                "horizontal_Et_Ht_diagnostic_relative": {k: v["relative_l2_no_phase_fit"] for k, v in comp["same_coordinate_fields"]["horizontal_Et_Ht_diagnostics_only"].items()},
            }
            for comp in comparisons
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
