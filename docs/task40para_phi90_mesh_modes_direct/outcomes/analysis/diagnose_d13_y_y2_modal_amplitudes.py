"""Offline modal-amplitude audit for the saved D13 B/X/Y/Z/Y2 runs.

Reads only the small port diffraction/amplitude JSON files and run identity
text. It does not load fields, resources, or solver state.
"""
from __future__ import annotations

import cmath
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path("results/si_block_phi90_50x50_17x20_h120")
OUT = Path(
    "docs/task40para_phi90_mesh_modes_direct/outcomes/records/"
    "d13_y_y2_modal_amplitude_diagnostic.json"
)
CASES = {
    "B": ("task40_phi90_13p5_D13_B_p6_direct_v1", "20261016T091948.653032Z"),
    "X": ("task40_phi90_13p5_D13_X_p6_direct_v1", "20261016T094950.200837Z"),
    "Y": ("task40_phi90_13p5_D13_Y_p6_direct_v1", "20261016T102453.831934Z"),
    "Z": ("task40_phi90_13p5_D13_Z_p6_direct_v1", "20261016T104423.676151Z"),
    "Y2": ("task40_phi90_13p5_D13_Y2_p6_direct_v1", "20261016T112452.011352Z"),
}
AMPLITUDE_FIELDS = (
    "auxiliary_amplitude_total_projection",
    "outgoing_amplitude",
    "outgoing_amplitude_at_boundary",
)
IDENTITY_FIELDS = (
    "side",
    "direction",
    "medium",
    "m",
    "n",
    "polarization",
    "alpha",
    "gamma",
    "beta",
    "kz",
    "refractive_index",
    "propagating",
    "power_carrying",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def as_complex(value: list[float]) -> complex:
    return complex(float(value[0]), float(value[1]))


def key(row: dict) -> tuple:
    return (
        row["side"],
        row["direction"],
        int(row["m"]),
        int(row["n"]),
        row["polarization"],
    )


def read_case(label: str) -> dict:
    run_name, stamp = CASES[label]
    run = ROOT / f"{run_name}__full3d_direct__mpi1__Mna" / stamp
    output = run / "numerical_output"
    modal_path = output / "dtn_port_diffraction_orders_3d.json"
    auxiliary_path = output / "dtn_auxiliary_amplitudes_3d.json"
    modal = json.loads(modal_path.read_text(encoding="utf-8"))
    auxiliary = json.loads(auxiliary_path.read_text(encoding="utf-8"))
    rows = modal["orders"]
    aux_by_key = {key(row): row for row in auxiliary}
    if len(rows) != 612 or len(aux_by_key) != 612:
        raise ValueError(f"{label}: expected 612 modal records")
    if [key(row) for row in rows] != [key(row) for row in auxiliary]:
        raise ValueError(f"{label}: modal and auxiliary output ordering differs")
    cross_file_fields = (
        "beta",
        "kz",
        "propagating",
        "auxiliary_amplitude_total_projection",
        "incident_projection",
        "outgoing_amplitude",
        "boundary_phase",
        "outgoing_amplitude_at_boundary",
    )
    cross_file_exact = all(
        all(row[name] == aux_by_key[key(row)][name] for name in cross_file_fields)
        for row in rows
    )
    if not cross_file_exact:
        raise ValueError(f"{label}: auxiliary and diffraction modal fields differ")
    return {
        "label": label,
        "run": run,
        "modal_path": modal_path,
        "auxiliary_path": auxiliary_path,
        "modal": modal,
        "rows": rows,
        "auxiliary_output_matches_diffraction_orders_exactly": cross_file_exact,
        "metrics": modal["metrics"],
        "identity": {
            name: (run / name).read_text(encoding="utf-8").strip()
            for name in ("source_sha.txt", "input_sha256.txt", "physical_model_sha256.txt")
        },
    }


def norm_record(reference: np.ndarray, candidate: np.ndarray, mask: np.ndarray) -> dict:
    delta = candidate[mask] - reference[mask]
    ref = reference[mask]
    cand = candidate[mask]
    return {
        "count": int(mask.sum()),
        "reference_l2": float(np.linalg.norm(ref)),
        "candidate_l2": float(np.linalg.norm(cand)),
        "delta_l2": float(np.linalg.norm(delta)),
        "relative_to_reference_l2": (
            float(np.linalg.norm(delta) / np.linalg.norm(ref))
            if np.linalg.norm(ref)
            else None
        ),
    }


def main() -> None:
    cases = {label: read_case(label) for label in CASES}
    base_rows = cases["Y"]["rows"]
    base_keys = [key(row) for row in base_rows]
    if any([key(row) for row in case["rows"]] != base_keys for case in cases.values()):
        raise ValueError("B/X/Y/Z/Y2 mode keys/order differ")
    if any(
        [{name: row[name] for name in IDENTITY_FIELDS} for row in case["rows"]]
        != [{name: row[name] for name in IDENTITY_FIELDS} for row in base_rows]
        for case in cases.values()
    ):
        raise ValueError("B/X/Y/Z/Y2 mode/branch/material identity differs")

    reference = cases["Y"]
    candidate = cases["Y2"]
    reference_rows = reference["rows"]
    candidate_rows = candidate["rows"]
    phases_exact = all(
        left["boundary_phase"] == right["boundary_phase"]
        for left, right in zip(reference_rows, candidate_rows, strict=True)
    )
    incident_power = {
        label: case["metrics"]["incident_power_code_units"]
        for label, case in cases.items()
    }
    if len(set(incident_power.values())) != 1:
        raise ValueError("incident power normalization differs across cases")

    propagating = np.asarray([bool(row["propagating"]) for row in reference_rows])
    carrying = np.asarray([bool(row["power_carrying"]) for row in reference_rows])
    masks = {
        "all_612": np.ones(612, dtype=bool),
        "propagating": propagating,
        "power_carrying": carrying,
        "evanescent_flag_not_propagating": ~propagating,
        "not_power_carrying": ~carrying,
    }
    amplitudes = {}
    for field in AMPLITUDE_FIELDS:
        ref = np.asarray([as_complex(row[field]) for row in reference_rows])
        cand = np.asarray([as_complex(row[field]) for row in candidate_rows])
        delta = cand - ref
        full_delta_sq = float(np.vdot(delta, delta).real)
        classes = {}
        for name, mask in masks.items():
            part = norm_record(ref, cand, mask)
            part_delta_sq = float(np.vdot(delta[mask], delta[mask]).real)
            part["fraction_of_all_612_delta_l2_squared"] = (
                part_delta_sq / full_delta_sq if full_delta_sq else 0.0
            )
            classes[name] = part
        pair_mask = np.asarray(
            [
                row["side"] == "top"
                and int(row["m"]) in (-4, 4)
                and int(row["n"]) == 0
                and row["polarization"] == "p"
                for row in reference_rows
            ],
            dtype=bool,
        )
        pair_delta_sq = float(np.vdot(delta[pair_mask], delta[pair_mask]).real)
        amplitudes[field] = {
            "reference_case": "Y",
            "candidate_case": "Y2",
            "full_612": norm_record(ref, cand, masks["all_612"]),
            "groups": classes,
            "top_m_pm4_n0_p_pair": {
                "count": int(pair_mask.sum()),
                "delta_l2": float(np.linalg.norm(delta[pair_mask])),
                "fraction_of_all_612_delta_l2_squared": (
                    pair_delta_sq / full_delta_sq if full_delta_sq else 0.0
                ),
            },
        }

    selected = []
    for m in (-4, 4):
        rows_by_case = {}
        for label, case in cases.items():
            row = next(
                row
                for row in case["rows"]
                if row["side"] == "top"
                and int(row["m"]) == m
                and int(row["n"]) == 0
                and row["polarization"] == "p"
            )
            raw = as_complex(row["outgoing_amplitude"])
            auxiliary = as_complex(row["auxiliary_amplitude_total_projection"])
            incident = as_complex(row["incident_projection"])
            phase = as_complex(row["boundary_phase"])
            boundary = as_complex(row["outgoing_amplitude_at_boundary"])
            projected = raw * phase
            expected_raw = auxiliary - incident
            rows_by_case[label] = {
                **{name: row[name] for name in IDENTITY_FIELDS},
                "auxiliary_amplitude_total_projection": row[
                    "auxiliary_amplitude_total_projection"
                ],
                "incident_projection": row["incident_projection"],
                "outgoing_amplitude": row["outgoing_amplitude"],
                "boundary_phase": row["boundary_phase"],
                "boundary_phase_abs": abs(phase),
                "outgoing_amplitude_at_boundary": row[
                    "outgoing_amplitude_at_boundary"
                ],
                "raw_to_boundary_abs_error": abs(projected - boundary),
                "raw_convention_abs_error": abs(raw - expected_raw),
                "modal_power_code_units": row["modal_power_code_units"],
                "power_ratio": row["power_ratio"],
                "R": row["R"],
                "T": row["T"],
            }
        selected.append({"side": "top", "m": m, "n": 0, "polarization": "p", "cases": rows_by_case})

    transform_checks = {}
    for label, case in cases.items():
        max_raw_convention_error = 0.0
        max_raw_to_boundary_error = 0.0
        max_boundary_phase_formula_error = 0.0
        max_power_ratio_error = 0.0
        for row in case["rows"]:
            raw = as_complex(row["outgoing_amplitude"])
            aux = as_complex(row["auxiliary_amplitude_total_projection"])
            incident = as_complex(row["incident_projection"])
            phase = as_complex(row["boundary_phase"])
            boundary = as_complex(row["outgoing_amplitude_at_boundary"])
            raw_expected = aux - incident if row["side"] == "top" else aux
            z_ref = (
                case["metrics"]["dtn_port_top_reference_z"]
                if row["side"] == "top"
                else case["metrics"]["dtn_port_bottom_reference_z"]
            )
            phase_expected = cmath.exp(1j * as_complex(row["kz"]) * z_ref)
            power_ratio_expected = (
                row["modal_power_code_units"]
                / case["metrics"]["incident_power_code_units"]
            )
            max_raw_convention_error = max(
                max_raw_convention_error, abs(raw - raw_expected)
            )
            max_raw_to_boundary_error = max(
                max_raw_to_boundary_error, abs(raw * phase - boundary)
            )
            max_boundary_phase_formula_error = max(
                max_boundary_phase_formula_error, abs(phase - phase_expected)
            )
            max_power_ratio_error = max(
                max_power_ratio_error,
                abs(float(row["power_ratio"]) - power_ratio_expected),
            )
        transform_checks[label] = {
            "auxiliary_json_matches_diffraction_json_exactly": case[
                "auxiliary_output_matches_diffraction_orders_exactly"
            ],
            "max_abs_raw_outgoing_convention_error": max_raw_convention_error,
            "max_abs_raw_times_boundary_phase_error": max_raw_to_boundary_error,
            "max_abs_boundary_phase_formula_error": max_boundary_phase_formula_error,
            "max_abs_power_ratio_reconstruction_error": max_power_ratio_error,
        }

    record = {
        "schema": "task40_d13_y_y2_modal_amplitude_diagnostic_v1",
        "scope": "offline small modal JSON audit only; no field archive, resource stream, FE, or factor read",
        "comparison": {
            "reference": "Y",
            "candidate": "Y2",
            "mode_count": 612,
            "mode_keys_and_order_equal_B_X_Y_Z_Y2": True,
            "mode_beta_material_flags_equal_B_X_Y_Z_Y2": True,
            "boundary_phase_exact_equal_Y_Y2_all_612": phases_exact,
            "reference_planes_nm": {
                "top": reference["metrics"]["dtn_port_top_reference_z"],
                "bottom": reference["metrics"]["dtn_port_bottom_reference_z"],
            },
            "amplitude_convention": reference["metrics"]["dtn_port_modal_amplitude_convention"],
            "incident_power_code_units_by_case": incident_power,
            "transform_and_export_checks": transform_checks,
            "projection_denominator_source_formula": "area * electric_tangential_norm_sq * abs(boundary_phase)^2; the eigenvector norm itself is not serialized in these small modal artifacts",
            "amplitude_norm_reference": "Y vector L2; delta is Y2 minus Y; subset delta shares use squared L2 contribution / all-612 squared delta norm",
            "group_masks_overlap": "propagating and power_carrying overlap; evanescent_flag_not_propagating is the stored not-propagating flag; not_power_carrying is also reported",
        },
        "source_artifacts": {
            label: {
                "run_dir": str(case["run"]),
                **case["identity"],
                "diffraction_orders_json_sha256": sha256(case["modal_path"]),
                "auxiliary_amplitudes_json_sha256": sha256(case["auxiliary_path"]),
                "active_mode_count": len(case["rows"]),
            }
            for label, case in cases.items()
        },
        "group_counts": {name: int(mask.sum()) for name, mask in masks.items()},
        "y_to_y2_amplitude_norms": amplitudes,
        "selected_top_evanescent_modes": selected,
        "interpretation_limits": [
            "The raw-to-boundary conversion is reproduced from the saved outgoing coefficient and exact saved boundary_phase; it does not remove the Y/Y2 difference because the same phase is used in both cases.",
            "The top (m=±4,n=0,p) modes are non-propagating and not power-carrying; their amplitude anomaly does not contribute to reported R/T, but remains part of the all-612 amplitude comparison.",
            "This audit rules out a mode-key/order mismatch or a Y/Y2 boundary-phase mismatch in the saved modal outputs. It does not prove the underlying FE modal solution is accurate or identify the numerical cause of its mesh sensitivity.",
            "No canonical pillar-sidewall trace comparison is present in these modal outputs.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(OUT)
    print(sha256(OUT))
    for field, result in amplitudes.items():
        print(field, json.dumps(result["full_612"], sort_keys=True))
        print("  groups", json.dumps(result["groups"], sort_keys=True))
        print("  top pair", json.dumps(result["top_m_pm4_n0_p_pair"], sort_keys=True))
    for entry in selected:
        print("selected", entry["m"])
        for label, row in entry["cases"].items():
            print(label, "raw", row["outgoing_amplitude"], "phase", row["boundary_phase"], "boundary", row["outgoing_amplitude_at_boundary"], "power", row["modal_power_code_units"], row["power_ratio"])


if __name__ == "__main__":
    main()
