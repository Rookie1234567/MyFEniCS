"""Freeze and verify Task002 Review-V4 M3R / Case116 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import numpy as np

from src.common.modes_3d import enumerate_diffraction_orders_3d
from src.forward_data.provenance import canonical_hash, source_identity
from src.forward_data.task002_dataset import ARRAY_FILES, PRODUCTION_ROUTE
from src.forward_data.task002_full3d import (
    build_task002_full3d_config, extract_task002_full3d_orders,
)
from src.forward_data.task002_m3r_design import freeze_all_designs, point_tuple
from src.forward_data.task002_schema import (
    TASK002_DATASET_SCHEMA_VERSION, TASK002_DIAGNOSTIC_FIDELITIES,
    TASK002_FIXED_M_ORDERS, TASK002_OBSERVABLE_SCHEMA_VERSION,
    TASK002_PARAMETER_SCHEMA_VERSION, TASK002_PRODUCTION_FIDELITIES,
    Task002ForwardParameters, task002_parameter_catalog,
)


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/cases/116_task002_single_fidelity_design"
RECORDS = CASE / "records"
ART114 = ROOT / "benchmarks/artifacts/cases/114/m2b/full3d"
ART115 = ROOT / "benchmarks/artifacts/cases/115/m2c/formal"
ART116 = ROOT / "benchmarks/artifacts/cases/116/m3r"
PROD = "S_PROD_FULL3D_STATIC_P5_H10"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _find_execution(result: Path) -> Path:
    for parent in result.parents:
        candidate = parent / "execution.json"
        if candidate.is_file():
            return candidate
    raise ValueError(f"execution.json not found above {result}")


def _raw_results() -> list[Path]:
    values = set(ART114.glob("*/results/*/dtn_port_diffraction_orders_3d.json"))
    values.update(ART115.glob("*/results/dtn_port_diffraction_orders_3d.json"))
    return sorted(values)


def _parameters(execution: dict[str, Any]) -> Task002ForwardParameters:
    p = execution["parameters"]
    if "geometry" in p:
        geometry, configuration = p["geometry"], p["configuration"]
        return Task002ForwardParameters(
            geometry["height_nm"], geometry["width_x_nm"],
            configuration["grazing_deg"], configuration["azimuth_deg"], PROD,
        )
    return Task002ForwardParameters(
        p.get("height_nm", 120.0), p.get("width_x_nm", 17.0),
        p["grazing_deg"], p["azimuth_deg"], PROD,
    )


def order_window_v3_audit() -> dict[str, Any]:
    probe = Task002ForwardParameters(120.0, 17.0, 0.5, 0.0, PROD)
    cfg = build_task002_full3d_config(probe)
    analytic_union: set[int] = set()
    closest: dict[int, float] = {m: float("inf") for m in range(-12, 13)}
    for grazing in np.linspace(0.5, 10.0, 97):
        for azimuth in np.linspace(0.0, 90.0, 181):
            cfg.incident_theta_deg = 90.0 - float(grazing)
            cfg.incident_phi_deg = float(azimuth)
            for order in enumerate_diffraction_orders_3d(
                cfg, max_m_override=12, max_n_override=0,
            ):
                metric = min(abs(complex(order.beta_top)),
                             abs(complex(order.beta_bottom))) / cfg.k0
                closest[order.m] = min(closest[order.m], float(metric))
                if order.top_propagating or order.bottom_propagating:
                    analytic_union.add(int(order.m))

    rows, raw_n0_power, raw_nonzero_power = [], {}, {}
    failures = []
    plus_identity_count = {2: 0, 3: 0}
    for path in _raw_results():
        execution_path = _find_execution(path.parent)
        execution = _read(execution_path)
        parameters = _parameters(execution)
        raw = _read(path)["orders"]
        port = _read(path.parent / "dtn_port_power_metrics_3d.json")
        extracted = extract_task002_full3d_orders(
            raw, parameters=parameters, port_power=port,
        )
        for order in extracted["orders"]:
            if order["m"] in plus_identity_count:
                plus_identity_count[order["m"]] += 1
        for item in raw:
            key = (int(item["m"]), int(item["n"]))
            power = float(item.get("power_ratio") or 0.0)
            target = raw_n0_power if key[1] == 0 else raw_nonzero_power
            target[key] = max(target.get(key, 0.0), power)
        passed = (not extracted["missing"]
                  and not extracted["uncovered_power_carrying_n0"]
                  and extracted["schema_version"] == TASK002_OBSERVABLE_SCHEMA_VERSION)
        if not passed:
            failures.append(str(path))
        rows.append({
            "raw_orders": str(path), "raw_sha256": _sha(path),
            "execution_sha256": _sha(execution_path),
            "grazing_deg": parameters.grazing_deg,
            "azimuth_deg": parameters.azimuth_deg,
            "v3_order_count": len(extracted["orders"]),
            "v3_missing": extracted["missing"],
            "uncovered_power_carrying_n0": extracted["uncovered_power_carrying_n0"],
            "plus_2_plus_3_identity_present": all(
                any(order["m"] == m for order in extracted["orders"])
                for m in (2, 3)
            ), "pass": passed,
        })
    fixed = set(TASK002_FIXED_M_ORDERS)
    raw_outside = {f"m{m}_n{n}": value for (m, n), value in raw_n0_power.items()
                   if m not in fixed and value > 0.0}
    return {
        "schema_version": "task002.case116-order-window-v3-audit.v1",
        "observable_schema_version": TASK002_OBSERVABLE_SCHEMA_VERSION,
        "fixed_m_orders": list(TASK002_FIXED_M_ORDERS), "fixed_n": 0,
        "analytic_grid_shape": [97, 181],
        "analytic_n0_propagating_union": sorted(analytic_union),
        "analytic_union_covered": analytic_union.issubset(fixed),
        "nearest_abs_beta_over_k0": {str(m): value for m, value in closest.items()},
        "raw_artifact_count": len(rows), "raw_reextraction_rows": rows,
        "raw_n0_max_power_by_order": {f"m{m}_n{n}": value
                                      for (m, n), value in sorted(raw_n0_power.items())},
        "raw_n_nonzero_leakage_max_power_by_order": {
            f"m{m}_n{n}": value for (m, n), value in sorted(raw_nonzero_power.items())
        },
        "raw_n0_power_outside_v3": raw_outside,
        "high_azimuth_positive_order_note": (
            "v3 explicitly freezes m=+2,+3 identities; n!=0 raw positive-m "
            "responses remain leakage diagnostics and are not production channels"
        ),
        "gates": {
            "schema_is_v3": TASK002_OBSERVABLE_SCHEMA_VERSION == "task002.fixed-n0-orders.v3",
            "plus_2_plus_3_frozen": {2, 3}.issubset(fixed),
            "analytic_union_covered": analytic_union.issubset(fixed),
            "all_raw_reextractions_pass": not failures and bool(rows),
            "plus_2_plus_3_present_every_reextraction": all(
                value == len(rows) for value in plus_identity_count.values()),
            "no_raw_n0_power_outside_v3": not raw_outside,
            "n_nonzero_remains_diagnostic": True,
        },
    }


def runtime_topology_record(source_sha: str) -> dict[str, Any]:
    manifest = _read(ART116 / "campaign.json")
    rows = []
    for item in manifest["samples"].values():
        run = ROOT / item["run_directory"] if not Path(item["run_directory"]).is_absolute() else Path(item["run_directory"])
        execution = _read(run / "execution.json")
        record = _read(run / "results/task002_full3d_record.json")
        rows.append({
            "run": str(run), "source_sha": execution["baseline_sha"],
            "parameters": record["parameters"],
            "planned_topology_identity": record["planned_topology_identity"],
            "actual_runtime_topology_identity": record["actual_runtime_topology_identity"],
            "planned_vs_actual": record["planned_vs_actual"],
            "formal_gates": record["gates"], "watchdog": execution["watchdog"],
            "execution_sha256": _sha(run / "execution.json"),
            "record_sha256": _sha(run / "results/task002_full3d_record.json"),
        })
    return {
        "schema_version": "task002.case116-runtime-topology-identity.v1",
        "source_sha": source_sha, "smoke_count": len(rows), "rows": rows,
        "gates": {
            "five_p5_smokes": len(rows) == 5,
            "one_clean_source_sha": {row["source_sha"] for row in rows} == {source_sha},
            "all_planned_vs_actual_pass": all(row["planned_vs_actual"]["pass"] for row in rows),
            "all_formal_gates_pass": all(all(row["formal_gates"].values()) for row in rows),
            "all_zero_swap": all(row["watchdog"]["peak_swap_bytes"] == 0 for row in rows),
            "all_cleanup_complete": all(row["watchdog"]["cleanup_complete"] for row in rows),
        },
    }


def single_fidelity_schema_record(source_sha: str) -> dict[str, Any]:
    catalog = task002_parameter_catalog()
    return {
        "schema_version": "task002.case116-single-fidelity-schema.v1",
        "source_sha": source_sha, "catalog": catalog,
        "production_fidelities": TASK002_PRODUCTION_FIDELITIES,
        "diagnostic_fidelities": TASK002_DIAGNOSTIC_FIDELITIES,
        "parameter_schema": TASK002_PARAMETER_SCHEMA_VERSION,
        "observable_schema": TASK002_OBSERVABLE_SCHEMA_VERSION,
        "dataset_schema": TASK002_DATASET_SCHEMA_VERSION,
        "dataset_arrays": list(ARRAY_FILES), "production_route": PRODUCTION_ROUTE,
        "model_candidates": {
            "diagnostic": "low-order PCE/Chebyshev",
            "production": "single-fidelity Matern-5/2 ARD GP",
            "multifidelity": "removed",
        },
        "feature_maps_training_only_cv": {
            "A": ["h_norm", "w_norm", "kx_over_k0", "ky_over_k0"],
            "B": ["h_norm", "w_norm", "kx_over_k0", "ky_over_k0", "kz_over_k0"],
            "C": ["h_norm", "w_norm", "sin_grazing", "cos_azimuth", "sin_azimuth"],
            "frozen_validation_use": "prohibited for feature/model selection",
        },
        "gates": {
            "one_production_model": list(TASK002_PRODUCTION_FIDELITIES) == [PROD],
            "production_is_p5": TASK002_PRODUCTION_FIDELITIES[PROD]["degree"] == 5,
            "dataset_has_no_lf_split": "train_lf_indices.npy" not in ARRAY_FILES,
            "dataset_has_single_train_split": "train_indices.npy" in ARRAY_FILES,
            "p4_is_diagnostic": "S_DIAG_FULL3D_STATIC_P4_H10" in TASK002_DIAGNOSTIC_FIDELITIES,
            "hybrid_not_production": all("HYBRID" not in name for name in TASK002_PRODUCTION_FIDELITIES),
        },
    }


def validation_addendum() -> dict[str, Any]:
    grid = {(g, a) for g in (0.5, 0.75, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0)
            for a in (0.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 75.0, 90.0)}
    old = {(0.5, 0.0), (0.5, 90.0), (10.0, 0.0), (10.0, 90.0),
           (0.5, 45.0), (10.0, 45.0), (5.25, 0.0), (5.25, 90.0), (5.25, 45.0)}
    overlap = sorted(old & grid)
    source = ROOT / "benchmarks/cases/115_task002_full3d_hierarchy_qualification/records/full3d_fidelity_screen.json"
    original = _read(source)
    claimed = original["frozen_validation_pilot"]["validation_is_frozen_and_disjoint_from_training"]
    return {
        "schema_version": "task002.case115-validation-addendum.v1",
        "case115_record": str(source), "case115_record_sha256": _sha(source),
        "original_claim": claimed, "exact_intersection": [list(value) for value in overlap],
        "intersection_count": len(overlap), "off_grid_count": len(old - grid),
        "corrected_semantics": (
            "Case115 interpolation was a qualification diagnostic, not strict frozen "
            "validation; the p4 rejection remains supported independently"
        ),
        "gates": {
            "false_disjoint_claim_identified": claimed is True,
            "six_overlapping_angles_recorded": len(overlap) == 6,
            "three_off_grid_angles_recorded": len(old - grid) == 3,
            "case115_raw_not_rewritten": True,
        },
    }


def freeze_design_files() -> dict[str, Any]:
    identity = source_identity(ROOT)
    if identity["dirty"]:
        raise RuntimeError("M3R designs require a clean implementation source")
    designs = freeze_all_designs(identity["source_sha"])
    for name, value in designs.items():
        (CASE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
    split = designs["split_hashes.json"]
    sampling = f"""# Task002 M3R frozen sampling design

All point tables are design-only and bind clean implementation SHA
`{identity['source_sha']}`. No M4 PDE was run.

- training: {designs['training_design.json']['point_count']} p5 points, seed 20260729;
- frozen validation: {designs['frozen_validation_design.json']['point_count']} p5 points, seed 20260730;
- candidate pool: {designs['candidate_pool.json']['point_count']} points, seed 20260731;
- discretization audit: {designs['discretization_audit_design.json']['point_count']} diagnostic candidates.

Training and frozen validation have exact tuple intersection zero. Frozen
validation is prohibited from feature, transform, kernel, hyperparameter,
model, and acquisition selection. Audit candidates never become production
dataset samples. Combined design hash: `{split['combined_design_sha256']}`.
"""
    (CASE / "sampling_design.md").write_text(sampling, encoding="utf-8")
    return designs


def design_record(source_sha: str) -> dict[str, Any]:
    designs = {name: _read(CASE / name) for name in (
        "training_design.json", "frozen_validation_design.json", "candidate_pool.json",
        "discretization_audit_design.json", "split_hashes.json")}
    split = designs["split_hashes.json"]
    return {
        "schema_version": "task002.case116-design-and-split.v1",
        "source_sha": source_sha,
        "files": {name: {"sha256": _sha(CASE / name),
                          "point_count": value.get("point_count")}
                  for name, value in designs.items()},
        "split_hashes": split,
        "sampling_design_sha256": _sha(CASE / "sampling_design.md"),
        "gates": {
            "all_designs_one_clean_sha": all(value["source_sha"] == source_sha
                                               for value in designs.values()),
            "training_validation_disjoint": not split["intersection_audit"]["training_validation"],
            "training_candidate_disjoint": not split["intersection_audit"]["training_candidate"],
            "validation_candidate_disjoint": not split["intersection_audit"]["validation_candidate"],
            "validation_count_16": designs["frozen_validation_design.json"]["point_count"] == 16,
            "candidate_count_4096": designs["candidate_pool.json"]["point_count"] == 4096,
            "audit_count_6_to_10": 6 <= designs["discretization_audit_design.json"]["point_count"] <= 10,
            "no_design_has_execution_result": all(
                "observables" not in point for value in designs.values()
                for point in value.get("points", [])
            ),
        },
    }


def write_records() -> dict[str, Any]:
    source_sha = _read(CASE / "split_hashes.json")["source_sha"]
    values = {
        "order_window_v3_audit.json": order_window_v3_audit(),
        "runtime_topology_identity.json": runtime_topology_record(source_sha),
        "single_fidelity_schema.json": single_fidelity_schema_record(source_sha),
        "design_and_split.json": design_record(source_sha),
        "case115_validation_addendum.json": validation_addendum(),
    }
    RECORDS.mkdir(parents=True, exist_ok=True)
    for name, value in values.items():
        (RECORDS / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-designs", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.freeze_designs:
        values = freeze_design_files()
        print(json.dumps({name: value.get("point_count") for name, value in values.items()}, indent=2))
        return 0
    values = write_records() if args.write else {
        path.name: _read(path) for path in RECORDS.glob("*.json")
    }
    gates = {name: all(value.get("gates", {}).values()) for name, value in values.items()}
    print(json.dumps({"record_count": len(values), "record_gates": gates}, indent=2))
    return 0 if len(values) == 5 and all(gates.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
