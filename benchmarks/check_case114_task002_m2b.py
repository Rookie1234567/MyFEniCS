"""Build independently checked compact records for Task002 Review-V2 M2B."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.forward_data.task002_m2b import AZIMUTH_DEG, GRAZING_DEG


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/cases/114_task002_solver_domain_robustness"
RECORDS = CASE / "records"
P_POINTS = ((0.5, 15.0), (0.5, 45.0), (2.0, 15.0), (10.0, 45.0))
SELECTED = (
    *((0.5, a) for a in AZIMUTH_DEG),
    (1.0, 45.0), (10.0, 45.0),
)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tag(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def _full_dir(artifacts: Path, degree: int, g: float, a: float, h: float = 10.0) -> Path:
    prefix = f"p{degree}" if h == 10.0 else f"p{degree}h{_tag(h)}"
    return artifacts / "full3d" / f"{prefix}_g{_tag(g)}_a{_tag(a)}"


def _hybrid_dir(artifacts: Path, degree: int, g: float, a: float, route: str) -> Path:
    return artifacts / "hybrid" / f"p{degree}_g{_tag(g)}_a{_tag(a)}_{route}"


def _result_dir(run: Path) -> Path:
    candidates = list((run / "results").glob("*/run_summary.json"))
    if len(candidates) != 1:
        raise ValueError(f"expected one Full3D result below {run}, got {len(candidates)}")
    return candidates[0].parent


def _compact_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in orders:
        result.append({
            "side": row["side"], "m": int(row["m"]), "n": int(row["n"]),
            "polarization": row["polarization"],
            "propagating": bool(row["propagating"]),
            "power_carrying": row.get("power_carrying", row.get("propagating")),
            "outgoing_amplitude_at_boundary": row["outgoing_amplitude_at_boundary"],
            "power_ratio": row.get("power_ratio"),
        })
    return result


def _full(run: Path, include_orders: bool = True) -> dict[str, Any]:
    execution_path = run / "execution.json"
    execution = _read(execution_path)
    result = _result_dir(run)
    summary = _read(result / "run_summary.json")
    power = _read(result / "dtn_port_power_metrics_3d.json")
    volume = _read(result / "volume_absorption.json")
    order_file = result / "dtn_port_diffraction_orders_3d.json"
    row: dict[str, Any] = {
        "run": str(run), "source_sha": execution["baseline_sha"],
        "parameters": execution["parameters"],
        "status": summary["case_status"],
        "R_total": power["R_total"], "T_total": power["T_total"],
        "A_balance": power["A_balance"], "A_volume": volume["A_volume_total"],
        "volume_closure_error": power["energy_closure_error_dtn_port_modal_volume"],
        "full_relative_residual": summary["linear_system_relative_residual"],
        "nedelec_dofs": summary["num_nedelec_dofs"],
        "watchdog": execution["watchdog"],
        "execution_sha256": _sha(execution_path),
        "orders_sha256": _sha(order_file),
    }
    if include_orders:
        row["orders"] = _compact_orders(_read(order_file)["orders"])
    return row


def _hybrid(run: Path, include_orders: bool = True, include_qep: bool = False) -> dict[str, Any]:
    execution_path, solver_path = run / "execution.json", run / "solver_record.json"
    execution, solver = _read(execution_path), _read(solver_path)
    illumination = execution["parameters"]["configuration"]["illumination"]
    fidelity = execution["parameters"]["fidelity"]
    port = solver["validation"]["port_power"]
    volume = solver["physical_field_reconstruction"]["volume_absorption"]
    propagation = solver["hybrid_system"]["internal_propagation"]
    row: dict[str, Any] = {
        "run": str(run), "source_sha": execution["baseline_sha"],
        "degree": fidelity["degree"], "grazing_deg": illumination["grazing_deg"],
        "azimuth_deg": illumination["azimuth_deg"],
        "route": execution["parameters"]["solver_route_id"],
        "status": solver["status"], "formal_gate_pass": all(solver["gates"].values()),
        "failed_gates": [key for key, value in solver["gates"].items() if not value],
        "gates": solver["gates"],
        "true_relative_residual": solver["solve"]["true_relative_residual"],
        "R_total": port["R_total"], "T_total": port["T_total"],
        "A_balance": port["A_balance"], "A_volume": volume["A_volume_total"],
        "volume_closure_error": volume["energy_closure_error"],
        "max_biorthogonality_identity_error": max(
            solver["qep"][side]["max_biorthogonality_identity_error"]
            for side in ("positive", "negative")
        ),
        "internal_propagation": propagation,
        "local_energy": volume["local_regions"],
        "middle_energy": volume["middle_modal_region"],
        "watchdog": execution["watchdog"],
        "execution_sha256": _sha(execution_path), "solver_sha256": _sha(solver_path),
    }
    if include_orders:
        row["orders"] = _compact_orders(solver["validation"]["external_diffraction_orders"])
    if include_qep:
        row["qep"] = solver["qep"]
    return row


def _order_map(row: dict[str, Any]) -> dict[tuple[Any, ...], dict[str, Any]]:
    return {
        (item["side"], item["m"], item["n"], item["polarization"]): item
        for item in row["orders"]
    }


def _order_delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, float | int]:
    a, b = _order_map(left), _order_map(right)
    keys = sorted(set(a) & set(b))
    amplitude = []
    power = []
    for key in keys:
        za = complex(*a[key]["outgoing_amplitude_at_boundary"])
        zb = complex(*b[key]["outgoing_amplitude_at_boundary"])
        amplitude.append(abs(za - zb))
        pa, pb = a[key].get("power_ratio"), b[key].get("power_ratio")
        if pa is not None and pb is not None:
            power.append(abs(float(pa) - float(pb)))
    return {
        "common_order_channels": len(keys),
        "max_complex_amplitude_abs_error": max(amplitude, default=math.nan),
        "max_power_ratio_abs_error": max(power, default=math.nan),
        "missing_order_channels": len(set(a) ^ set(b)),
    }


def _observable_delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, float]:
    return {key: abs(float(left[key]) - float(right[key]))
            for key in ("R_total", "T_total", "A_balance", "A_volume")}


def full3d_p_reference(artifacts: Path) -> dict[str, Any]:
    rows = []
    by_key = {}
    for g, a in P_POINTS:
        for degree in (3, 4, 5):
            row = _full(_full_dir(artifacts, degree, g, a))
            rows.append(row); by_key[(g, a, degree, 10.0)] = row
        href = _full(_full_dir(artifacts, 4, g, a, 7.5))
        rows.append(href); by_key[(g, a, 4, 7.5)] = href
    comparisons = []
    for g, a in P_POINTS:
        for left, right in ((3, 4), (4, 5)):
            x, y = by_key[(g, a, left, 10.0)], by_key[(g, a, right, 10.0)]
            comparisons.append({"point": [g, a], "left": f"p{left}/h10",
                                "right": f"p{right}/h10",
                                "observables": _observable_delta(x, y),
                                "orders": _order_delta(x, y)})
        x, y = by_key[(g, a, 4, 7.5)], by_key[(g, a, 5, 10.0)]
        comparisons.append({"point": [g, a], "left": "p4/h7.5",
                            "right": "p5/h10", "observables": _observable_delta(x, y),
                            "orders": _order_delta(x, y)})
    projection = by_key[(0.5, 15.0, 5, 10.0)]["watchdog"]
    return {
        "schema_version": "task002.case114-full3d-p-reference.v1",
        "rows": rows, "comparisons": comparisons,
        "resource_result": {
            "p5_max_peak_rss_bytes": max(
                row["watchdog"]["peak_rss_bytes"] for row in rows
                if row["parameters"]["degree"] == 5
            ),
            "p5_peak_swap_bytes": projection["peak_swap_bytes"],
            "p4_h7p5_max_peak_rss_bytes": max(
                row["watchdog"]["peak_rss_bytes"] for row in rows
                if row["parameters"]["h_nm"] == 7.5
            ),
            "all_cleanup_complete": all(row["watchdog"]["cleanup_complete"] for row in rows),
        },
        "disposition": "p4_h10_underresolved; p4_h7p5_and_p5_h10_select_the_p5_branch",
    }


def axial_model_ab(artifacts: Path) -> dict[str, Any]:
    rows, pairs = [], []
    for degree in (4, 5, 6):
        for azimuth in (15.0, 45.0):
            route_rows = {}
            for route in ("continuous", "discrete"):
                row = _hybrid(_hybrid_dir(artifacts, degree, 0.5, azimuth, route))
                rows.append(row); route_rows[route] = row
            reference_degree = degree if degree <= 5 else 5
            reference = _full(_full_dir(artifacts, reference_degree, 0.5, azimuth))
            pairs.append({
                "degree": degree, "grazing_deg": 0.5, "azimuth_deg": azimuth,
                "route_observable_delta": _observable_delta(
                    route_rows["continuous"], route_rows["discrete"]),
                "route_order_delta": _order_delta(
                    route_rows["continuous"], route_rows["discrete"]),
                "continuous_to_reference": _observable_delta(route_rows["continuous"], reference),
                "discrete_to_reference": _observable_delta(route_rows["discrete"], reference),
                "reference_identity": f"Full3D_p{reference_degree}_h10",
            })
    return {"schema_version": "task002.case114-axial-model-ab.v1",
            "rows": rows, "pairs": pairs,
            "interpretation": "axial route changes are measured independently of QEP mode selection"}


def floquet_probe(artifacts: Path) -> dict[str, Any]:
    rows = [_read(path) for path in sorted((artifacts / "probes").glob("*.json"))]
    pairs = []
    for degree in range(1, 7):
        for g, a in ((0.5, 15), (0.5, 45), (2, 30), (10, 45)):
            pair = [r for r in rows if r["degree"] == degree
                    and r["grazing_deg"] == g and r["azimuth_deg"] == a]
            pair.sort(key=lambda r: r["mpi_ranks"])
            if len(pair) != 2:
                raise ValueError(f"missing MPI pair p{degree} {g}/{a}")
            invariant_keys = ("full_global_size", "reduced_global_size", "global_slave_count",
                              "transverse_constraint_count", "longitudinal_constraint_count")
            pairs.append({
                "degree": degree, "point": [g, a],
                "partition_invariant_counts_equal": all(pair[0][k] == pair[1][k] for k in invariant_keys),
                "phase_x_abs_delta": abs(
                    complex(pair[0]["phase_x"]["real"], pair[0]["phase_x"]["imag"]) -
                    complex(pair[1]["phase_x"]["real"], pair[1]["phase_x"]["imag"])),
                "phase_y_abs_delta": abs(
                    complex(pair[0]["phase_y"]["real"], pair[0]["phase_y"]["imag"]) -
                    complex(pair[1]["phase_y"]["real"], pair[1]["phase_y"]["imag"])),
                "raw_global_numbering_sha_equal": pair[0]["deterministic_full_vector_sha256"] == pair[1]["deterministic_full_vector_sha256"],
                "raw_sha_note": "not a gate: DOLFINx global numbering is partition dependent",
            })
    return {
        "schema_version": "task002.case114-floquet-probe.v1", "rows": rows, "mpi_pairs": pairs,
        "all_48_probe_gates_pass": len(rows) == 48 and all(all(r["gates"].values()) for r in rows),
        "max_analytic_probe_residual": max(r["analytic_quasiperiodic_reconstruction_relative_residual"] for r in rows),
        "max_slave_row_residual": max(r["random_free_vector_max_slave_row_relative_residual"] for r in rows),
        "max_explicit_chac_error": max(r["explicit_chac_action_relative_error"] for r in rows),
        "all_partition_invariant_identities_pass": all(
            p["partition_invariant_counts_equal"] and p["phase_x_abs_delta"] <= 1e-15
            and p["phase_y_abs_delta"] <= 1e-15 for p in pairs
        ),
    }


def _mode_transition(previous: Path, current: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    with np.load(previous) as left, np.load(current) as right:
        for side in ("positive", "negative"):
            a, b = left[f"{side}_vectors"], right[f"{side}_vectors"]
            an = a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-300)
            bn = b / np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-300)
            overlap = np.abs(an @ bn.conj().T)
            row, column = linear_sum_assignment(-overlap)
            qa, _ = np.linalg.qr(a.T)
            qb, _ = np.linalg.qr(b.T)
            singular = np.linalg.svd(qa.conj().T @ qb, compute_uv=False)
            result[side] = {
                "permutation": column.tolist(),
                "matched_overlap_min": float(np.min(overlap[row, column])),
                "matched_overlap_mean": float(np.mean(overlap[row, column])),
                "subspace_angle_max_deg": float(np.degrees(np.arccos(np.clip(np.min(singular), 0, 1)))),
            }
    return result


def mode_continuation(artifacts: Path) -> dict[str, Any]:
    degrees = []
    for degree in (4, 5, 6):
        identities, transitions = [], []
        previous = None
        for azimuth in AZIMUTH_DEG:
            run = _hybrid_dir(artifacts, degree, 0.5, azimuth, "discrete")
            solver = _read(run / "solver_record.json")
            identity = {"azimuth_deg": azimuth, "status": solver["status"],
                        "failed_gates": [k for k, v in solver["gates"].items() if not v]}
            for side in ("positive", "negative"):
                q = dict(solver["qep"][side]); q.pop("full_vector_gathered", None)
                identity[side] = q
            identities.append(identity)
            archive = run / "solver_record.modes.npz"
            if previous is not None:
                transitions.append({"from_azimuth_deg": previous[0], "to_azimuth_deg": azimuth,
                                    **_mode_transition(previous[1], archive)})
            previous = (azimuth, archive)
        degrees.append({"degree": degree, "identities": identities, "transitions": transitions})
    failure = _read(_hybrid_dir(artifacts, 6, 0.5, 45.0, "discrete") / "solver_record.json")
    positive = failure["qep"]["positive"]
    diag = positive["biorthogonality_identity_diagnostics"]
    rows = sorted({diag["worst_row_index"], diag["worst_entry_row"], diag["worst_entry_column"]})
    groups = [group for group in positive["near_degenerate_groups"]
              if set(group["indices"]) & set(rows)]
    return {
        "schema_version": "task002.case114-mode-continuation.v1", "degrees": degrees,
        "p6_phi45_failure_block": {
            "classification": "near_degenerate_block_partition_split",
            "diagnostics": diag, "involved_mode_indices": rows,
            "involved_near_degenerate_groups": groups,
            "betas_per_nm": {str(i): positive["betas_per_nm"][i] for i in rows},
            "polynomial_relative_residuals": {str(i): positive["polynomial_relative_residuals"][i] for i in rows},
            "reason": "worst off-diagonal pair crosses adjacent 114/115 and 116/117 blocks although their betas are nearly coincident",
        },
    }


def energy_identity(artifacts: Path) -> dict[str, Any]:
    rows = []
    for degree in (4, 5, 6):
        for azimuth in (15.0, 45.0):
            run = _hybrid_dir(artifacts, degree, 0.5, azimuth, "discrete")
            row = _hybrid(run)
            raw_sum = sum(float(x["power_ratio"]) for x in row["orders"]
                          if x["power_ratio"] is not None)
            rows.append({
                "degree": degree, "grazing_deg": 0.5, "azimuth_deg": azimuth,
                "incident_normalization": "each run's recorded incident normal power",
                "bottom_local": row["local_energy"]["bottom"],
                "top_local": row["local_energy"]["top"],
                "middle_modal": row["middle_energy"],
                "external_dtn": {
                    "raw_auxiliary_modal_power_sum": raw_sum,
                    "recorded_R_plus_T": row["R_total"] + row["T_total"],
                    "auxiliary_power_identity_error": raw_sum - row["R_total"] - row["T_total"],
                },
                "whole_domain": {"A_balance": row["A_balance"], "A_volume": row["A_volume"],
                                 "closure_error": row["volume_closure_error"]},
                "failed_gates": row["failed_gates"],
            })
    return {"schema_version": "task002.case114-energy-identity.v1", "rows": rows}


def angle_robustness(artifacts: Path) -> dict[str, Any]:
    rows = []
    for g in GRAZING_DEG:
        for a in AZIMUTH_DEG:
            hybrid = _hybrid(_hybrid_dir(artifacts, 4, g, a, "discrete"))
            full = _full(_full_dir(artifacts, 4, g, a))
            rows.append({
                "grazing_deg": g, "azimuth_deg": a,
                "hybrid_status": hybrid["status"], "formal_gate_pass": hybrid["formal_gate_pass"],
                "failed_gates": hybrid["failed_gates"],
                "same_p_observable_error": _observable_delta(hybrid, full),
                "same_p_order_error": _order_delta(hybrid, full),
                "biorthogonality_identity_error": hybrid["max_biorthogonality_identity_error"],
                "hybrid_RTA": [hybrid["R_total"], hybrid["T_total"], hybrid["A_balance"]],
                "full3d_RTA": [full["R_total"], full["T_total"], full["A_balance"]],
            })
    selected = []
    for g, a in SELECTED:
        by_degree = {}
        for degree in (5, 6):
            hybrid = _hybrid(_hybrid_dir(artifacts, degree, g, a, "discrete"))
            reference_degree = degree if degree == 5 else 5
            full = _full(_full_dir(artifacts, reference_degree, g, a))
            by_degree[f"p{degree}"] = {
                "hybrid": hybrid, "reference": f"Full3D_p{reference_degree}_h10",
                "observable_error": _observable_delta(hybrid, full),
                "order_error": _order_delta(hybrid, full),
            }
        selected.append({"grazing_deg": g, "azimuth_deg": a, "degrees": by_degree})
    max_rta = max(max(row["same_p_observable_error"][k]
                      for k in ("R_total", "T_total", "A_balance")) for row in rows)
    return {
        "schema_version": "task002.case114-angle-robustness-map.v1",
        "rows": rows, "selected_higher_order_points": selected,
        "summary": {"angle_count": len(rows),
                    "formal_pass_count": sum(row["formal_gate_pass"] for row in rows),
                    "formal_fail_count": sum(not row["formal_gate_pass"] for row in rows),
                    "max_same_p_RTA_abs_error": max_rta},
    }


def routing_map(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    angle = records["angle_robustness_map.json"]
    mode = records["mode_continuation.json"]
    p_ref = records["full3d_p_reference.json"]
    return {
        "schema_version": "task002.case114-solver-routing-map.v1",
        "selected_route": "Route 4: Hybrid paused; Full3D static hierarchy required",
        "m3_authorized": False,
        "reasons": [
            f"Hybrid p4 passes only {angle['summary']['formal_pass_count']}/80 formal Gates",
            "Full3D p4/h7.5 follows the Full3D p5/h10 response branch, proving p4/h10 under-resolution",
            "Hybrid p5 matches same-p Full3D p5, so the p-branch jump is not caused by Hybrid coupling",
            "Hybrid p6 retains a p6/0.5deg/45deg biorthogonality failure caused by split near-degenerate blocks",
        ],
        "qualified_now": {
            "diagnostic_reference": "Full3D static p5/h10 at tested reference/selected points",
            "low_order_negative_result": p_ref["disposition"],
            "floquet_constraints": "qualified p1-p6 MPI1/2 on 4 double-Floquet probes",
        },
        "not_yet_qualified": {
            "uniform_low_fidelity": "Full3D p4/h7.5 has only A-D anchors, not an 80-angle domain map",
            "hybrid_high_fidelity": mode["p6_phi45_failure_block"]["classification"],
        },
        "resume_condition": "Review V3 must authorize either p4/h7.5 domain qualification or a revised Full3D hierarchy; M3 remains closed",
        "route_identity_required_per_sample": True,
        "bulk_generation_allowed": False, "surrogate_training_allowed": False,
        "angle_doe_allowed": False, "inversion_allowed": False,
    }


def build_records(artifacts: Path) -> dict[str, dict[str, Any]]:
    records = {
        "full3d_p_reference.json": full3d_p_reference(artifacts),
        "axial_model_ab.json": axial_model_ab(artifacts),
        "floquet_probe.json": floquet_probe(artifacts),
        "mode_continuation.json": mode_continuation(artifacts),
        "energy_identity.json": energy_identity(artifacts),
        "angle_robustness_map.json": angle_robustness(artifacts),
    }
    records["solver_routing_map.json"] = routing_map(records)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--write-records", action="store_true")
    parser.add_argument("--check-records", action="store_true")
    args = parser.parse_args()
    records = build_records(args.artifact_root.resolve())
    if args.write_records:
        RECORDS.mkdir(parents=True, exist_ok=True)
        for name, value in records.items():
            (RECORDS / name).write_text(
                json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
            )
    if args.check_records:
        expected = _read(CASE / "expected.json")
        for name in expected["required_records"]:
            path = RECORDS / name
            if not path.is_file():
                raise ValueError(f"missing Case114 record: {name}")
            if name in records and _read(path) != records[name]:
                raise ValueError(f"stale Case114 record: {name}")
        if records["angle_robustness_map.json"]["summary"]["angle_count"] != 80:
            raise ValueError("M2B angle map is incomplete")
        if not records["floquet_probe.json"]["all_48_probe_gates_pass"]:
            raise ValueError("M2B Floquet probe Gate failed")
    print(json.dumps({name: value.get("schema_version") for name, value in records.items()}, indent=2))


if __name__ == "__main__":
    main()
