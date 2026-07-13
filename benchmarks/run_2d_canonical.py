from __future__ import annotations

import argparse
import json
import resource
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from src.common.config import SimulationConfig
from src.solvers.solve_port_maxwell import run_port_case
from src.solvers.solve_te_maxwell import run_te_port_case
from src.solvers.solve_vector_maxwell import _json_default


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "benchmarks" / "cases"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _complex(value: object) -> complex:
    if isinstance(value, (int, float, complex)):
        return complex(value)
    return complex(str(value).replace("I", "j").replace("i", "j"))


def _config_from_contract(
    contract: dict[str, Any], *, polarization: str
) -> SimulationConfig:
    physical = contract["physical_model"]
    numerical = contract["numerical_settings"]
    return SimulationConfig(
        case_name=str(contract["case_id"]) + "_" + polarization.lower(),
        calculation_method="port",
        constraint_backend="manual",
        port_boundary_model="dtn",
        scattering_background=str(contract.get("scattering_background", "layered")),
        polarization_type=polarization,
        period_x=float(physical["period_x_nm"]),
        air_height=float(physical["air_height_nm"]),
        substrate_thickness=float(physical["substrate_thickness_nm"]),
        grating_width=float(physical["grating_width_nm"]),
        grating_height=float(physical["grating_height_nm"]),
        lambda0=float(physical["wavelength_nm"]),
        incident_angle_deg=float(physical["incident_angle_deg"]),
        n_air=_complex(physical["n_air"]),
        n_substrate=_complex(physical["n_substrate"]),
        n_grating=_complex(physical["n_grating"]),
        use_pml=False,
        port_use_pml=False,
        port_dtn_order_count=int(numerical["port_dtn_order_count"]),
        port_dtn_assembly=str(numerical.get("port_dtn_assembly", "auxiliary")),
        port_use_diffraction_orders=bool(
            numerical.get("port_use_diffraction_orders", False)
        ),
        port_rayleigh_tolerance=float(numerical.get("port_rayleigh_tolerance", 1.0e-6)),
        compute_power_metrics=True,
        diffraction_order_count=int(numerical.get("diffraction_order_count", 2)),
        power_probe_num_points=int(numerical.get("power_probe_num_points", 512)),
        nedelec_degree=int(numerical["degree"]),
        visualization_degree=int(numerical.get("visualization_degree", 1)),
        generate_png_plots=False,
        mesh_target_size=float(numerical["mesh_target_size_nm"]),
        mesh_cell_shape=str(numerical.get("mesh_cell_shape", "triangle")),
        mesh_lock_near_field_template=bool(
            numerical.get("mesh_lock_near_field_template", False)
        ),
        unique_output=False,
    )


def _peak_rss_mb() -> float:
    usage = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return usage / 1024.0 if sys.platform != "darwin" else usage / (1024.0**2)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _metadata(args: argparse.Namespace, actual_command: str) -> dict[str, Any]:
    return {
        "commit_sha": args.source_commit,
        "branch": args.source_branch,
        "git_dirty": bool(args.source_git_dirty),
        "tracked_source_dirty": bool(args.source_tracked_dirty),
        "command": actual_command,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "container_image": args.container_image,
        "container_digest": args.container_digest,
        "host_environment_id": args.host_environment_id,
        "provenance": "canonical_lightweight_rerun_from_frozen_case_contract",
    }


def _actual_command(args: argparse.Namespace) -> str:
    return "python -m benchmarks.run_2d_canonical " + " ".join(
        shlex.quote(value) for value in sys.argv[1:]
    )


def _official_metrics(summary: dict[str, Any], *, auxiliary: bool) -> dict[str, Any]:
    key = "dtn_auxiliary_power_metrics" if auxiliary else "dtn_port_power_metrics"
    metrics = dict(summary[key])
    R = float(metrics["R_total"])
    T = float(metrics["T_total"])
    A_volume = float(metrics.get("A_volume", metrics.get("A_volume_total", 0.0)))
    A_balance = float(1.0 - R - T)
    return {
        "method": (
            "dtn_auxiliary_modal_amplitudes"
            if auxiliary
            else "dtn_boundary_trace_modal_projection"
        ),
        "R_total": R,
        "T_total": T,
        "A_balance": A_balance,
        "A_volume": A_volume,
        "R_plus_T_plus_A_volume": R + T + A_volume,
        "energy_closure_error": 1.0 - R - T - A_volume,
        "orders": metrics.get("orders", []),
    }


def _diagnostic_probe(summary: dict[str, Any]) -> dict[str, Any]:
    metrics = summary.get("power_metrics") or {}
    R = metrics.get("R_total")
    T = metrics.get("T_total")
    A = metrics.get("A_volume", metrics.get("A_volume_total"))
    closure = None
    if R is not None and T is not None and A is not None:
        closure = 1.0 - float(R) - float(T) - float(A)
    return {
        "identity": "diagnostic_only",
        "R_total": R,
        "T_total": T,
        "A_volume": A,
        "energy_closure_error": closure,
        "must_not_replace_official": True,
    }


def _record(
    *,
    benchmark_id: str,
    case_id: str,
    polarization: str,
    cfg: SimulationConfig,
    summary: dict[str, Any],
    official: dict[str, Any],
    metadata: dict[str, Any],
    artifact_directory: Path,
) -> dict[str, Any]:
    dofs = summary.get("num_nedelec_dofs", summary.get("num_scalar_dofs"))
    return {
        "benchmark_id": benchmark_id,
        "case_id": case_id,
        "polarization": polarization,
        "metadata": metadata,
        "physical_model": {
            "period_x_nm": cfg.period_x,
            "air_height_nm": cfg.air_height,
            "substrate_thickness_nm": cfg.substrate_thickness,
            "grating_width_nm": cfg.grating_width,
            "grating_height_nm": cfg.grating_height,
            "wavelength_nm": cfg.lambda0,
            "incident_angle_deg": cfg.incident_angle_deg,
            "n_air": [cfg.n_air.real, cfg.n_air.imag],
            "n_substrate": [cfg.n_substrate.real, cfg.n_substrate.imag],
            "n_grating": [cfg.n_grating.real, cfg.n_grating.imag],
            "time_convention": "exp(-i omega t)",
        },
        "resolved_config": cfg.as_jsonable(),
        "artifact_root": _relative(artifact_directory.parent),
        "artifact_directory": _relative(artifact_directory),
        "artifact_provenance": "full fields and logs are gitignored; this JSON is the lightweight canonical record",
        "mesh": {
            "cells": int(summary["num_mesh_cells"]),
            "field_dofs": int(dofs),
            "auxiliary_dofs": int(summary.get("num_auxiliary_dofs", 0)),
            "reduced_dofs": int(summary["num_reduced_dofs"]),
            "mesh_target_size_nm": cfg.mesh_target_size,
            "element": "N1curl" if polarization == "TM" else "Lagrange",
            "degree": cfg.nedelec_degree,
        },
        "matrix": {
            "rows": summary.get("linear_matrix_rows"),
            "nnz": summary.get("linear_matrix_nnz"),
            "reduced_rows": summary.get("num_reduced_dofs"),
            "reduced_nnz": summary.get("reduced_matrix_nnz"),
        },
        "solver": {
            "backend": summary["solver"],
            "linear_true_residual": summary["reduced_linear_residual"],
        },
        "official_rta": official,
        "diagnostic_probe": _diagnostic_probe(summary),
        "auxiliary_vs_trace": summary.get(
            "dtn_auxiliary_vs_trace_power_difference", {}
        ),
        "elapsed_seconds": float(summary["elapsed_seconds"]),
        "process_peak_rss_mb_after_run": _peak_rss_mb(),
        "rss_measurement_scope": "serial process ru_maxrss after this run",
        "status": "pass",
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _run_case002(args: argparse.Namespace) -> None:
    contract_path = CASES / "002_2d_tm_dtn_equivalence" / "config.json"
    contract = _load_json(contract_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = args.artifact_root / f"case002_{stamp}"
    results: dict[str, tuple[SimulationConfig, dict[str, Any], np.ndarray, Path]] = {}
    for assembly in ("explicit", "auxiliary"):
        cfg = _config_from_contract(contract, polarization="TM")
        cfg.port_dtn_assembly = assembly
        cfg.case_name = f"case002_tm_dtn_{assembly}"
        vectors: list[np.ndarray] = []
        out_dir = root / assembly
        summary = run_port_case(
            cfg, out_dir, "manual", solution_observer=vectors.append
        )
        if len(vectors) != 1:
            raise RuntimeError("solution observer did not receive exactly one vector")
        results[assembly] = (cfg, summary, vectors[0], out_dir)

    explicit_cfg, explicit_summary, explicit_vector, explicit_dir = results["explicit"]
    auxiliary_cfg, auxiliary_summary, auxiliary_vector, auxiliary_dir = results[
        "auxiliary"
    ]
    if explicit_vector.shape != auxiliary_vector.shape:
        raise RuntimeError("explicit and auxiliary FE vectors have different shapes")
    denominator = max(float(np.linalg.norm(auxiliary_vector)), 1.0e-30)
    field_difference = float(
        np.linalg.norm(explicit_vector - auxiliary_vector) / denominator
    )
    explicit_rta = _official_metrics(explicit_summary, auxiliary=False)
    auxiliary_rta = _official_metrics(auxiliary_summary, auxiliary=True)
    comparison = {
        "benchmark_id": "case002_explicit_vs_auxiliary",
        "case_id": contract["case_id"],
        "metadata": _metadata(args, _actual_command(args)),
        "field_relative_difference": field_difference,
        "absolute_differences": {
            name: abs(float(explicit_rta[name]) - float(auxiliary_rta[name]))
            for name in ("R_total", "T_total", "A_volume", "energy_closure_error")
        },
        "explicit": {
            "field_dofs": explicit_summary["num_nedelec_dofs"],
            "auxiliary_dofs": explicit_summary.get("num_auxiliary_dofs", 0),
            "matrix_rows": explicit_summary["linear_matrix_rows"],
            "matrix_nnz": explicit_summary["linear_matrix_nnz"],
            "reduced_rows": explicit_summary["num_reduced_dofs"],
            "reduced_nnz": explicit_summary["reduced_matrix_nnz"],
            "linear_true_residual": explicit_summary["reduced_linear_residual"],
            "official_rta": explicit_rta,
            "elapsed_seconds": explicit_summary["elapsed_seconds"],
        },
        "auxiliary": {
            "field_dofs": auxiliary_summary["num_nedelec_dofs"],
            "auxiliary_dofs": auxiliary_summary.get("num_auxiliary_dofs", 0),
            "matrix_rows": auxiliary_summary["linear_matrix_rows"],
            "matrix_nnz": auxiliary_summary["linear_matrix_nnz"],
            "reduced_rows": auxiliary_summary["num_reduced_dofs"],
            "reduced_nnz": auxiliary_summary["reduced_matrix_nnz"],
            "linear_true_residual": auxiliary_summary["reduced_linear_residual"],
            "official_rta": auxiliary_rta,
            "elapsed_seconds": auxiliary_summary["elapsed_seconds"],
        },
        "artifact_root": _relative(root),
        "status": "pass",
    }
    expected = _load_json(CASES / "002_2d_tm_dtn_equivalence" / "expected.json")
    max_rta_delta = max(comparison["absolute_differences"].values())
    if field_difference > float(expected["field_relative_difference_max"]):
        raise RuntimeError(f"Case002 field difference failed: {field_difference}")
    if max_rta_delta > float(expected["rta_absolute_difference_max"]):
        raise RuntimeError(f"Case002 RTA difference failed: {max_rta_delta}")

    command = _actual_command(args)
    explicit_record = _record(
        benchmark_id="case002_explicit",
        case_id=contract["case_id"],
        polarization="TM",
        cfg=explicit_cfg,
        summary=explicit_summary,
        official=explicit_rta,
        metadata=_metadata(args, command),
        artifact_directory=explicit_dir,
    )
    auxiliary_record = _record(
        benchmark_id="case002_auxiliary",
        case_id=contract["case_id"],
        polarization="TM",
        cfg=auxiliary_cfg,
        summary=auxiliary_summary,
        official=auxiliary_rta,
        metadata=_metadata(args, command),
        artifact_directory=auxiliary_dir,
    )
    _write_json(args.record_dir / "explicit.json", explicit_record)
    _write_json(args.record_dir / "auxiliary.json", auxiliary_record)
    _write_json(args.record_dir / "comparison.json", comparison)


def _run_case003(args: argparse.Namespace) -> None:
    contract_path = CASES / "003_2d_te_tm_complex_absorption" / "config.json"
    contract = _load_json(contract_path)
    variant = str(args.variant).lower()
    if variant not in {"tm", "te"}:
        raise SystemExit("Case003 requires --variant tm or --variant te")
    variant_contract = dict(contract["variants"][variant])
    merged = {
        "case_id": contract["case_id"],
        "physical_model": variant_contract["physical_model"],
        "numerical_settings": variant_contract["numerical_settings"],
        "scattering_background": variant_contract.get(
            "scattering_background", "layered"
        ),
    }
    polarization = variant.upper()
    cfg = _config_from_contract(merged, polarization=polarization)
    cfg.case_name = f"case003_{variant}_complex_absorption"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.artifact_root / f"case003_{variant}_{stamp}"
    if variant == "tm":
        cfg.port_dtn_assembly = "auxiliary"
        summary = run_port_case(cfg, out_dir, "manual")
        official = _official_metrics(summary, auxiliary=True)
        benchmark_id = "case003_tm_lossy"
    else:
        summary = run_te_port_case(cfg, out_dir, "manual")
        official = _official_metrics(summary, auxiliary=False)
        benchmark_id = "case003_te_lossy"

    expected = _load_json(CASES / "003_2d_te_tm_complex_absorption" / "expected.json")
    tolerances = expected["tolerances"]
    residual = float(summary["reduced_linear_residual"])
    if residual > float(tolerances["linear_residual_max"]):
        raise RuntimeError(f"Case003 {variant} residual failed: {residual}")
    if abs(float(official["energy_closure_error"])) > float(
        tolerances["energy_closure_abs_max"]
    ):
        raise RuntimeError(
            f"Case003 {variant} energy closure failed: {official['energy_closure_error']}"
        )
    record = _record(
        benchmark_id=benchmark_id,
        case_id=contract["case_id"],
        polarization=polarization,
        cfg=cfg,
        summary=summary,
        official=official,
        metadata=_metadata(args, _actual_command(args)),
        artifact_directory=out_dir,
    )
    _write_json(args.record_dir / f"{variant}_complex_absorption.json", record)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate lightweight canonical records for 2D benchmark cases."
    )
    parser.add_argument("--case", choices=("002", "003"), required=True)
    parser.add_argument("--variant", choices=("tm", "te"))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--record-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--source-branch", default="codex/20260712-task28-stage-consolidation"
    )
    parser.add_argument("--source-git-dirty", action="store_true")
    parser.add_argument("--source-tracked-dirty", action="store_true")
    parser.add_argument("--container-image", required=True)
    parser.add_argument("--container-digest", required=True)
    parser.add_argument("--host-environment-id", default="task28_windows_wsl2_14gb")
    args = parser.parse_args(argv)
    args.artifact_root = (
        args.artifact_root
        if args.artifact_root.is_absolute()
        else ROOT / args.artifact_root
    )
    args.record_dir = (
        args.record_dir if args.record_dir.is_absolute() else ROOT / args.record_dir
    )
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    args.record_dir.mkdir(parents=True, exist_ok=True)
    if args.case == "002":
        _run_case002(args)
    else:
        _run_case003(args)


if __name__ == "__main__":
    main()
