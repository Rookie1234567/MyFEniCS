"""Build and verify compact Task002 Review-V1 M2A evidence records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from src.forward_data.task002_design import cutoff_diagnostics_v2
from src.forward_data.task002_m2a import MATRIX, STENCIL
from src.forward_data.task002_schema import Task002ForwardParameters


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks" / "cases" / "113_task002_m2a_low_grazing_diagnostics"
RECORDS = CASE / "records"
LF = "S_LF_HYBRID_P4_H10_M120"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_scaffold_record() -> dict[str, Any]:
    config = _read(CASE / "config.json")
    expected = _read(CASE / "expected.json")
    return {
        "schema_version": "task002.case113-scaffold.v1",
        "config_sha256": _sha256(CASE / "config.json"),
        "expected_sha256": _sha256(CASE / "expected.json"),
        "p_m_matrix": [list(item) for item in sorted(MATRIX)],
        "lf_stencil": [
            {"grazing_deg": g, "azimuth_deg": a} for g, a in sorted(STENCIL)
        ],
        "unchanged_gates": expected["unchanged_gates"],
        "raw_evidence_disposition": config["raw_case112_evidence_disposition"],
        "scope_gates": {
            "matrix_exact": len(MATRIX) == 6,
            "lf_stencil_exact": len(STENCIL) == 13,
            "formal_campaign_closed": not expected["formal_campaign_allowed"],
            "bulk_closed": not expected["bulk_generation_allowed"],
            "surrogate_closed": not expected["surrogate_training_allowed"],
        },
    }


def _hybrid_summary(run_directory: Path, *, evidence_role: str) -> dict[str, Any]:
    execution_path = run_directory / "execution.json"
    solver_path = run_directory / "solver_record.json"
    execution, solver = _read(execution_path), _read(solver_path)
    parameters = execution["parameters"]
    config = parameters["configuration"]
    fidelity = parameters["fidelity"]
    degree = int(fidelity["degree"])
    modes = int(parameters.get("diagnostic_requested_modes", fidelity["modes"]))
    port = solver["validation"]["port_power"]
    physical = solver["physical_field_reconstruction"]
    assembled = physical["assembled_interface_continuity"]
    volume = physical["volume_absorption"]
    watchdog = execution["watchdog"]
    return {
        "evidence_role": evidence_role, "run_directory": str(run_directory),
        "source_sha": execution["baseline_sha"], "degree": degree, "h_nm": 10.0,
        "requested_modes": modes, "grazing_deg": float(config["grazing_deg"]),
        "azimuth_deg": float(config["azimuth_deg"]), "polarization": "S",
        "status": solver["status"],
        "formal_gate_pass": all(bool(value) for value in solver["gates"].values()),
        "failed_formal_gates": [name for name, value in solver["gates"].items() if not value],
        "true_relative_residual": solver["solve"]["true_relative_residual"],
        "assembled_interface_e_max": max(
            assembled[side]["electric_tangential"]["relative_l2"]
            for side in ("bottom", "top")
        ),
        "exact_traction_dual_max": max(
            assembled[side]["traction_hcurl_dual"]["relative_dual"]
            for side in ("bottom", "top")
        ),
        "R_total": port["R_total"], "T_total": port["T_total"],
        "A_balance": port["A_balance"], "A_volume": volume["A_volume_total"],
        "energy_closure_error": volume["energy_closure_error"],
        "volume_ledger": volume,
        "wall_seconds": watchdog["elapsed_seconds"],
        "peak_rss_bytes": watchdog["peak_rss_bytes"],
        "peak_swap_bytes": watchdog["peak_swap_bytes"],
        "cleanup_complete": watchdog["cleanup_complete"],
        "execution_sha256": _sha256(execution_path),
        "solver_record_sha256": _sha256(solver_path),
    }


def _direct_summary(run_directory: Path) -> dict[str, Any]:
    execution_path = run_directory / "execution.json"
    execution = _read(execution_path)
    summaries = list((run_directory / "results").glob("*/run_summary.json"))
    if len(summaries) != 1:
        raise ValueError("Case113 Full3D run must contain one run_summary.json")
    summary_path = summaries[0]
    result_dir = summary_path.parent
    summary = _read(summary_path)
    volume = _read(result_dir / "volume_absorption.json")
    port = _read(result_dir / "dtn_port_power_metrics_3d.json")
    return {
        "schema_version": "task002.case113-direct-reference.v1",
        "method": "independent_Full3D_static_p4_h10",
        "source_sha": execution["baseline_sha"],
        "parameters": execution["parameters"],
        "R_total": port["R_total"], "T_total": port["T_total"],
        "A_balance": port["A_balance"], "A_volume": volume["A_volume_total"],
        "energy_closure_error": volume["energy_closure_error_port_volume"],
        "volume_ledger": volume,
        "incident_audit": {
            "mean_poynting_W_per_m2": summary.get("mean_poynting_W_per_m2"),
            "poynting_direction_cosine": summary.get("poynting_direction_cosine"),
        },
        "watchdog": execution["watchdog"],
        "execution_sha256": _sha256(execution_path),
        "run_summary_sha256": _sha256(summary_path),
    }


def _case112_reused_rows(artifact_root: Path, manifest_path: Path) -> list[dict[str, Any]]:
    manifest = _read(manifest_path)
    rows = []
    for key, item in manifest["samples"].items():
        p = item["parameters"]
        c, f = p["configuration"], p["fidelity"]
        point = (float(c["grazing_deg"]), float(c["azimuth_deg"]))
        if f["model_id"] == LF and point in {(0.5, 0.0), (0.5, 15.0), (0.5, 90.0)}:
            rows.append(_hybrid_summary(
                artifact_root / key[:16], evidence_role="immutable_case112_reuse",
            ))
    return rows


def build_records(
    artifact_root: Path, case112_artifact_root: Path, case112_manifest: Path,
) -> dict[str, dict[str, Any]]:
    new_hybrid = [
        _hybrid_summary(path, evidence_role="case113_diagnostic")
        for path in sorted(artifact_root.iterdir())
        if path.is_dir() and (path / "solver_record.json").is_file()
    ]
    matrix = [
        row for row in new_hybrid
        if (row["grazing_deg"], row["azimuth_deg"]) == (0.5, 15.0)
        and (row["degree"], row["requested_modes"]) in MATRIX
    ]
    if {(row["degree"], row["requested_modes"]) for row in matrix} != MATRIX:
        raise ValueError("Case113 p/M matrix is incomplete")
    direct = _direct_summary(artifact_root / "full3d_p4")
    p_m = {
        "schema_version": "task002.case113-p-m-convergence.v1",
        "center": {"height_nm": 120.0, "width_x_nm": 17.0,
                   "grazing_deg": 0.5, "azimuth_deg": 15.0, "polarization": "S"},
        "unchanged_energy_gate_abs": 1e-5,
        "rows": sorted(matrix, key=lambda row: (row["degree"], row["requested_modes"])),
    }
    reused = _case112_reused_rows(case112_artifact_root, case112_manifest)
    lf_new = [
        row for row in new_hybrid if row["degree"] == 4 and row["requested_modes"] == 120
        and (row["grazing_deg"], row["azimuth_deg"]) in STENCIL
    ]
    by_point: dict[tuple[float, float], dict[str, Any]] = {
        (row["grazing_deg"], row["azimuth_deg"]): row for row in reused
    }
    for row in lf_new:
        by_point.setdefault((row["grazing_deg"], row["azimuth_deg"]), row)
    if set(by_point) != STENCIL:
        raise ValueError(f"LF diagnostic stencil incomplete: {sorted(STENCIL - set(by_point))}")
    hf_rows = [
        row for row in new_hybrid if row["degree"] == 6 and row["requested_modes"] == 120
    ]
    angle = {
        "schema_version": "task002.case113-angle-stencil.v1",
        "lf_rows": [by_point[key] for key in sorted(by_point)],
        "hf_rows": sorted(hf_rows, key=lambda row: (row["grazing_deg"], row["azimuth_deg"])),
        "case112_raw_evidence_mutated": False,
    }
    p4 = next(row for row in matrix if (row["degree"], row["requested_modes"]) == (4, 120))
    p6 = next(row for row in matrix if (row["degree"], row["requested_modes"]) == (6, 120))
    direct["hybrid_deltas"] = {
        "p4": {name: p4[name] - direct[name] for name in ("R_total", "T_total", "A_balance", "A_volume")},
        "p6": {name: p6[name] - direct[name] for name in ("R_total", "T_total", "A_balance", "A_volume")},
    }
    ledger = {
        "schema_version": "task002.case113-energy-ledger.v1",
        "normalization": "all powers use each run's recorded incident normal power",
        "hybrid_p4_m120": p4["volume_ledger"],
        "hybrid_p6_m120": p6["volume_ledger"],
        "full3d_static_p4": direct["volume_ledger"],
        "required_terms": {
            "hybrid_local_bottom_top": True, "hybrid_middle_volume": True,
            "hybrid_middle_poynting_flux": True, "full3d_material_regions": True,
            "port_R_T_A_balance": True,
        },
    }
    cutoff_rows = []
    for grazing, azimuth in sorted(STENCIL):
        parameters = Task002ForwardParameters(120.0, 17.0, grazing, azimuth, LF)
        cutoff_rows.append({
            "grazing_deg": grazing, "azimuth_deg": azimuth,
            **cutoff_diagnostics_v2(parameters),
        })
    cutoff = {
        "schema_version": "task002.case113-cutoff-diagnostics-collection.v2",
        "rows": cutoff_rows,
        "incident_m0_is_not_nonzero_rayleigh": True,
    }
    return {
        "direct_reference.json": direct, "p_m_convergence.json": p_m,
        "angle_stencil.json": angle, "energy_ledger.json": ledger,
        "cutoff_diagnostics_v2.json": cutoff,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--case112-artifact-root", type=Path)
    parser.add_argument("--case112-manifest", type=Path)
    parser.add_argument("--write-records", action="store_true")
    parser.add_argument("--check-records", action="store_true")
    args = parser.parse_args()
    scaffold = build_scaffold_record()
    if not all(scaffold["scope_gates"].values()):
        raise ValueError("Case113 scaffold scope gate failed")
    result: dict[str, Any] = {"scaffold": scaffold}
    if args.artifact_root is not None:
        if args.case112_artifact_root is None or args.case112_manifest is None:
            parser.error("building M2A records requires both Case112 evidence paths")
        records = build_records(
            args.artifact_root, args.case112_artifact_root, args.case112_manifest,
        )
        if args.write_records:
            RECORDS.mkdir(parents=True, exist_ok=True)
            for name, value in records.items():
                (RECORDS / name).write_text(
                    json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                )
        result["records"] = records
    if args.check_records:
        tracked_scaffold = _read(RECORDS / "scaffold.json")
        if tracked_scaffold != scaffold:
            raise ValueError("Case113 scaffold record is stale")
        expected = _read(CASE / "expected.json")
        for name in expected["required_records"]:
            if not (RECORDS / name).is_file():
                raise ValueError(f"missing Case113 record: {name}")
        if args.artifact_root is not None:
            for name, value in result["records"].items():
                if _read(RECORDS / name) != value:
                    raise ValueError(f"stale Case113 record: {name}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
