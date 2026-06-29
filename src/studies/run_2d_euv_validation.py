from __future__ import annotations

import argparse
import csv
import json
import random
import time
from pathlib import Path

from ..common.config import project_root


def _json_default(value):
    if isinstance(value, complex):
        return [value.real, value.imag]
    if isinstance(value, Path):
        return str(value)
    return str(value)


BASE_EUV_ARGS = [
    "--polarization-type",
    "TM",
    "--period-x",
    "100.0",
    "--air-height",
    "100.0",
    "--substrate-thickness",
    "50.0",
    "--grating-width",
    "50.0",
    "--grating-height",
    "50.0",
    "--lambda0",
    "13.5",
    "--incident-angle-deg",
    "0.0",
    "--n-air",
    "1.0",
    "--n-substrate",
    "1.1",
    "--n-grating",
    "1.2",
    "--nedelec-degree",
    "2",
    "--visualization-degree",
    "3",
    "--compute-power-metrics",
    "--port-use-diffraction-orders",
    "--lock-near-field-template",
    "--near-field-margin-x",
    "25.0",
    "--near-field-air-top",
    "100.0",
    "--near-field-sub-depth",
    "50.0",
]


def _csv_list(text: str, cast):
    if not text:
        return []
    return [cast(item.strip()) for item in text.split(",") if item.strip()]


def _append_flag(args: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        args.extend([flag, str(value)])


def _case_args(*, mesh_size: float, cell_shape: str, extra: list[str] | None = None) -> list[str]:
    args = list(BASE_EUV_ARGS)
    _append_flag(args, "--mesh-target-size", mesh_size)
    _append_flag(args, "--mesh-cell-shape", cell_shape)
    args.extend(extra or [])
    return args


def _case_specs(study: str, args) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    shapes = _csv_list(args.cell_shapes, str)

    if study == "method_compare":
        for shape in shapes:
            specs.extend(
                [
                    {
                        "label": f"dtn_aux_{shape}",
                        "args": _case_args(
                            mesh_size=args.method_mesh_size,
                            cell_shape=shape,
                            extra=[
                                "--formulation",
                                "port",
                                "--constraint-backend",
                                "manual",
                                "--port-boundary-model",
                                "dtn",
                                "--port-dtn-assembly",
                                "auxiliary",
                            ],
                        ),
                    },
                    {
                        "label": f"dtn_explicit_{shape}",
                        "args": _case_args(
                            mesh_size=args.method_mesh_size,
                            cell_shape=shape,
                            extra=[
                                "--formulation",
                                "port",
                                "--constraint-backend",
                                "manual",
                                "--port-boundary-model",
                                "dtn",
                                "--port-dtn-assembly",
                                "explicit",
                            ],
                        ),
                    },
                    {
                        "label": f"robin_{shape}",
                        "args": _case_args(
                            mesh_size=args.method_mesh_size,
                            cell_shape=shape,
                            extra=[
                                "--formulation",
                                "port",
                                "--constraint-backend",
                                "manual",
                                "--port-boundary-model",
                                "robin",
                            ],
                        ),
                    },
                ]
            )
            if args.include_scattered_history:
                specs.append(
                    {
                        "label": f"scattered_layered_pml_{shape}",
                        "args": _case_args(
                            mesh_size=args.method_mesh_size,
                            cell_shape=shape,
                            extra=[
                                "--formulation",
                                "scattered",
                                "--constraint-backend",
                                "manual",
                                "--scattering-background",
                                "layered",
                                "--pml-top-thickness",
                                str(args.history_pml_thickness),
                                "--pml-bottom-thickness",
                                str(args.history_pml_thickness),
                            ],
                        ),
                    }
                )
        return specs

    if study == "mesh_convergence":
        for shape in shapes:
            for mesh_size in _csv_list(args.mesh_sizes, float):
                specs.append(
                    {
                        "label": f"mesh_{shape}_h{mesh_size:g}",
                        "args": _case_args(
                            mesh_size=mesh_size,
                            cell_shape=shape,
                            extra=[
                                "--formulation",
                                "port",
                                "--constraint-backend",
                                "manual",
                                "--port-boundary-model",
                                "dtn",
                                "--port-dtn-assembly",
                                "auxiliary",
                            ],
                        ),
                    }
                )
        return specs

    if study == "air_scan":
        for air_height in _csv_list(args.air_heights, float):
            specs.append(
                {
                    "label": f"air_{air_height:g}",
                    "args": _case_args(
                        mesh_size=args.scan_mesh_size,
                        cell_shape=args.scan_cell_shape,
                        extra=[
                            "--formulation",
                            "port",
                            "--constraint-backend",
                            "manual",
                            "--port-boundary-model",
                            "dtn",
                            "--port-dtn-assembly",
                            "auxiliary",
                            "--air-height",
                            str(air_height),
                        ],
                    ),
                }
            )
        return specs

    if study == "substrate_scan":
        for substrate_thickness in _csv_list(args.substrate_thicknesses, float):
            specs.append(
                {
                    "label": f"substrate_{substrate_thickness:g}",
                    "args": _case_args(
                        mesh_size=args.scan_mesh_size,
                        cell_shape=args.scan_cell_shape,
                        extra=[
                            "--formulation",
                            "port",
                            "--constraint-backend",
                            "manual",
                            "--port-boundary-model",
                            "dtn",
                            "--port-dtn-assembly",
                            "auxiliary",
                            "--substrate-thickness",
                            str(substrate_thickness),
                        ],
                    ),
                }
            )
        return specs

    if study == "combined_scan":
        rng = random.Random(args.random_seed)
        air_values = _csv_list(args.air_heights, float)
        substrate_values = _csv_list(args.substrate_thicknesses, float)
        pairs = [(a, s) for a in air_values for s in substrate_values]
        rng.shuffle(pairs)
        for air_height, substrate_thickness in pairs[: args.random_count]:
            specs.append(
                {
                    "label": f"combined_air{air_height:g}_sub{substrate_thickness:g}",
                    "args": _case_args(
                        mesh_size=args.scan_mesh_size,
                        cell_shape=args.scan_cell_shape,
                        extra=[
                            "--formulation",
                            "port",
                            "--constraint-backend",
                            "manual",
                            "--port-boundary-model",
                            "dtn",
                            "--port-dtn-assembly",
                            "auxiliary",
                            "--air-height",
                            str(air_height),
                            "--substrate-thickness",
                            str(substrate_thickness),
                        ],
                    ),
                }
            )
        return specs

    raise ValueError(f"Unknown study {study!r}.")


def _preferred_metrics(summary: dict[str, object]) -> dict[str, object]:
    for key in ("dtn_auxiliary_power_metrics", "dtn_port_power_metrics", "power_metrics"):
        metrics = summary.get(key, {})
        if isinstance(metrics, dict) and {"R_total", "T_total", "R_plus_T"}.issubset(metrics):
            return metrics
    return {}


def _extract_row(label: str, run_root: Path, summary: dict[str, object]) -> dict[str, object]:
    cfg = summary.get("config", {})
    metrics = _preferred_metrics(summary)
    near = summary.get("near_field_integrals") or metrics.get("near_field_integrals") or {}
    integrals = near.get("integral_abs_E2_dOmega", {}) if isinstance(near, dict) else {}
    means = near.get("mean_abs_E2", {}) if isinstance(near, dict) else {}
    return {
        "label": label,
        "run_root": str(run_root),
        "case_name": summary.get("case_name"),
        "cell_shape": cfg.get("mesh_cell_shape"),
        "mesh_target_size": cfg.get("mesh_target_size"),
        "air_height": cfg.get("air_height"),
        "substrate_thickness": cfg.get("substrate_thickness"),
        "port_boundary_model": cfg.get("port_boundary_model"),
        "port_dtn_assembly": cfg.get("port_dtn_assembly"),
        "R_total": metrics.get("R_total"),
        "T_total": metrics.get("T_total"),
        "R_plus_T": metrics.get("R_plus_T"),
        "energy_residual_1_minus_R_minus_T": metrics.get("energy_residual_1_minus_R_minus_T"),
        "I_grating": integrals.get("I_grating"),
        "I_air_near": integrals.get("I_air_near"),
        "I_sub_near": integrals.get("I_sub_near"),
        "mean_grating": means.get("mean_grating"),
        "mean_air_near": means.get("mean_air_near"),
        "mean_sub_near": means.get("mean_sub_near"),
        "reduced_linear_residual": summary.get("reduced_linear_residual"),
        "num_mesh_cells": summary.get("num_mesh_cells"),
        "num_nedelec_dofs": summary.get("num_nedelec_dofs"),
        "elapsed_seconds": summary.get("elapsed_seconds"),
    }


def _write_rows(out_dir: Path, rows: list[dict[str, object]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "study_summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    if not rows:
        return
    with (out_dir / "study_summary.csv").open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _run_study(study: str, args, out_dir: Path) -> list[dict[str, object]]:
    specs = _case_specs(study, args)
    if args.max_cases is not None:
        specs = specs[: args.max_cases]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "study_plan.json").write_text(
        json.dumps(specs, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    if args.dry_run:
        return []

    rows: list[dict[str, object]] = []
    for index, spec in enumerate(specs, start=1):
        label = str(spec["label"])
        case_args = list(spec["args"])
        print(f"[{study}] running {index}/{len(specs)}: {label}")
        from ..runners import run_cases

        comparison = run_cases.main(case_args)
        if comparison is None:
            raise RuntimeError("2D EUV study runner must be used in serial so run_cases.main returns a summary.")
        run_root = Path(str(comparison["run_root"]))
        summary_path = run_root / "all_run_summary.json"
        summaries = json.loads(summary_path.read_text(encoding="utf-8"))
        if not summaries:
            raise RuntimeError(f"No case summary was written for {label}.")
        rows.append(_extract_row(label, run_root, summaries[0]))
        _write_rows(out_dir, rows)
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run 2D EUV grating DtN validation studies.")
    parser.add_argument(
        "--study",
        choices=("method_compare", "mesh_convergence", "air_scan", "substrate_scan", "combined_scan", "all"),
        default="method_compare",
    )
    parser.add_argument("--mesh-sizes", default="4,3,2,1.5,1.25,1")
    parser.add_argument("--cell-shapes", default="triangle,quadrilateral")
    parser.add_argument("--method-mesh-size", type=float, default=4.0)
    parser.add_argument("--scan-mesh-size", type=float, default=1.5)
    parser.add_argument("--scan-cell-shape", choices=("triangle", "quadrilateral"), default="quadrilateral")
    parser.add_argument("--air-heights", default="60,70,80,90,110,120,150")
    parser.add_argument("--substrate-thicknesses", default="10,20,30,40,70,100")
    parser.add_argument("--random-seed", type=int, default=20260629)
    parser.add_argument("--random-count", type=int, default=8)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-scattered-history", action="store_true")
    parser.add_argument("--history-pml-thickness", type=float, default=50.0)
    parsed = parser.parse_args(argv)

    from mpi4py import MPI

    if MPI.COMM_WORLD.size != 1:
        raise SystemExit("2D DtN EUV validation studies use the serial manual DtN path; run without mpiexec.")

    root = project_root()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    study_names = (
        ["method_compare", "mesh_convergence", "air_scan", "substrate_scan", "combined_scan"]
        if parsed.study == "all"
        else [parsed.study]
    )
    for study in study_names:
        out_dir = root / "results" / "studies" / f"2D_EUV_{study}_{timestamp}"
        rows = _run_study(study, parsed, out_dir)
        print(f"[{study}] wrote {len(rows)} executed rows to {out_dir}")


if __name__ == "__main__":
    main()
