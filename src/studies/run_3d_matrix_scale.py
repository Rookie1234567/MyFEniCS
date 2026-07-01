from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ..common.config_3d import project_root


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _swap_used_mb() -> float | None:
    path = Path("/proc/meminfo")
    if not path.exists():
        return None
    values: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        parts = rest.strip().split()
        if not parts:
            continue
        try:
            values[key] = float(parts[0]) / 1024.0
        except ValueError:
            continue
    if "SwapTotal" not in values or "SwapFree" not in values:
        return None
    return max(values["SwapTotal"] - values["SwapFree"], 0.0)


def _load_summary(result_dir: Path) -> dict[str, Any] | None:
    all_summary = result_dir / "all_run_summary.json"
    run_summary = result_dir / "run_summary.json"
    if all_summary.exists():
        payload = json.loads(all_summary.read_text(encoding="utf-8"))
        if isinstance(payload, list) and payload:
            return payload[0]
    if run_summary.exists():
        return json.loads(run_summary.read_text(encoding="utf-8"))
    return None


def _extract_result_dir(stdout: str) -> Path | None:
    matches = re.findall(r"3D case results:\s*(.+)", stdout)
    if not matches:
        return None
    return Path(matches[-1].strip())


def _value(summary: dict[str, Any] | None, key: str, default=None):
    if summary is None:
        return default
    return summary.get(key, default)


def _matrix_value(summary: dict[str, Any] | None, key: str):
    stats = _value(summary, "matrix_stats", {}) or {}
    return stats.get(key)


def _timing_value(summary: dict[str, Any] | None, *keys: str):
    timings = _value(summary, "timings_seconds", {}) or {}
    for key in keys:
        value = timings.get(key)
        if value is not None:
            return value
    return None


def _row_from_result(
    *,
    mesh_target_size: float,
    mpi_procs: int,
    solver_profile: str,
    returncode: int,
    elapsed_wall_seconds: float,
    swap_before_mb: float | None,
    swap_after_mb: float | None,
    result_dir: Path | None,
    summary: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "mesh_target_size_nm": mesh_target_size,
        "mpi_procs": mpi_procs,
        "solver_profile": solver_profile,
        "returncode": returncode,
        "case_status": _value(summary, "case_status"),
        "result_dir": "" if result_dir is None else str(result_dir),
        "dof_raw_nedelec": _value(summary, "num_nedelec_dofs"),
        "floquet_constraints": _value(summary, "floquet_num_constraints"),
        "constrained_system_size": _value(summary, "constrained_linear_system_size"),
        "dtn_auxiliary_dofs": _value(summary, "stage4_dtn_num_auxiliary_dofs"),
        "matrix_rows": _matrix_value(summary, "matrix_rows"),
        "matrix_cols": _matrix_value(summary, "matrix_cols"),
        "nnz_used": _matrix_value(summary, "matrix_nnz_used"),
        "nnz_allocated": _matrix_value(summary, "matrix_nnz_allocated"),
        "average_nnz_per_row": _matrix_value(summary, "matrix_average_nnz_per_row"),
        "average_allocated_nnz_per_row": _matrix_value(summary, "matrix_average_allocated_nnz_per_row"),
        "petsc_matrix_memory_mb": _matrix_value(summary, "matrix_memory_mb"),
        "estimated_aij_matrix_memory_mb": _matrix_value(summary, "matrix_memory_estimate_mb"),
        "solve_time_seconds": _timing_value(
            summary,
            "linear_problem_solve",
            "stage4_dtn_linear_solve_seconds",
            "stage4_dtn_port_assembly_and_solve",
        ),
        "elapsed_wall_seconds": elapsed_wall_seconds,
        "summary_elapsed_seconds": _value(summary, "elapsed_seconds"),
        "peak_rss_mb": _value(summary, "max_rss_mb"),
        "swap_used_before_mb": swap_before_mb,
        "swap_used_after_mb": swap_after_mb,
        "swap_used_delta_mb": None
        if swap_before_mb is None or swap_after_mb is None
        else swap_after_mb - swap_before_mb,
        "actual_ksp_type": _value(summary, "actual_ksp_type"),
        "actual_pc_type": _value(summary, "actual_pc_type"),
        "actual_pc_factor_solver_type": _value(summary, "actual_pc_factor_solver_type"),
        "explicit_chac_constructed": _value(summary, "explicit_chac_constructed"),
        "dtn_augmented_to_base_nnz_ratio": (
            (_value(summary, "constraint_matrix_transform", {}) or {}).get("dtn_augmented_to_base_nnz_ratio")
        ),
        "constrained_to_unconstrained_nnz_ratio": (
            (_value(summary, "constraint_matrix_transform", {}) or {}).get("constrained_to_unconstrained_nnz_ratio")
        ),
        "R_total": _value(summary, "R_total"),
        "T_total": _value(summary, "T_total"),
        "R_plus_T": _value(summary, "R_plus_T"),
    }


def _command_for_case(args, mesh_size: float) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "src.runners.run_3d_cases",
        "--stage-case",
        args.stage_case,
        "--case",
        args.case,
        "--mesh-target-size",
        str(mesh_size),
        "--nedelec-degree",
        str(args.nedelec_degree),
        "--visualization-degree",
        str(args.visualization_degree),
        "--stage4-boundary-model",
        args.stage4_boundary_model,
        "--stage4-dtn-order-policy",
        args.stage4_dtn_order_policy,
        "--stage4-dtn-assembly",
        "auxiliary",
        "--petsc-direct-solver-profile",
        args.petsc_direct_solver_profile,
    ]
    if args.matrix_diagnostics_assemble_unconstrained:
        command.append("--matrix-diagnostics-assemble-unconstrained")
    for option in args.extra_runner_arg:
        command.extend(option.split())
    for option in args.petsc_option:
        if option.startswith("-"):
            command.append(option)
        else:
            command.extend(["--petsc-extra-option", option])
    if args.mpi_procs > 1:
        command = ["mpiexec", "-n", str(args.mpi_procs), *command]
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run 3D Maxwell matrix/solver scaling diagnostics and write CSV.")
    parser.add_argument("--mesh-sizes", type=float, nargs="+", default=[20.0, 15.0, 12.0, 10.0, 8.0])
    parser.add_argument("--mpi-procs", type=int, default=1)
    parser.add_argument("--stage-case", default="stage4_block_grating")
    parser.add_argument("--case", default="normal")
    parser.add_argument("--nedelec-degree", type=int, default=1)
    parser.add_argument("--visualization-degree", type=int, default=1)
    parser.add_argument("--stage4-boundary-model", default="dtn_port")
    parser.add_argument("--stage4-dtn-order-policy", default="zero_order")
    parser.add_argument(
        "--petsc-direct-solver-profile",
        choices=("default", "mumps_ooc", "mkl_pardiso", "mumps", "superlu_dist", "strumpack"),
        default="default",
    )
    parser.add_argument("--matrix-diagnostics-assemble-unconstrained", action="store_true")
    parser.add_argument("--petsc-option", action="append", default=[])
    parser.add_argument("--extra-runner-arg", action="append", default=[])
    parser.add_argument("--output-csv", default=None)
    parser.add_argument("--stop-on-failure", action="store_true")
    args = parser.parse_args(argv)

    root = project_root()
    out_dir = root / "results" / f"matrix_scale_{_timestamp()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = Path(args.output_csv) if args.output_csv else out_dir / "matrix_scale.csv"
    rows: list[dict[str, Any]] = []
    for mesh_size in args.mesh_sizes:
        command = _command_for_case(args, mesh_size)
        label = f"h={mesh_size:g}, np={args.mpi_procs}, solver={args.petsc_direct_solver_profile}"
        print(f"[matrix-scale] running {label}")
        print("[matrix-scale] command:", " ".join(command))
        swap_before = _swap_used_mb()
        t0 = time.perf_counter()
        proc = subprocess.run(command, cwd=root, text=True, capture_output=True)
        elapsed = time.perf_counter() - t0
        swap_after = _swap_used_mb()
        result_dir = _extract_result_dir(proc.stdout)
        summary = _load_summary(result_dir) if result_dir is not None else None
        (out_dir / f"run_h{str(mesh_size).replace('.', 'p')}_stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (out_dir / f"run_h{str(mesh_size).replace('.', 'p')}_stderr.txt").write_text(proc.stderr, encoding="utf-8")
        rows.append(
            _row_from_result(
                mesh_target_size=mesh_size,
                mpi_procs=args.mpi_procs,
                solver_profile=args.petsc_direct_solver_profile,
                returncode=proc.returncode,
                elapsed_wall_seconds=elapsed,
                swap_before_mb=swap_before,
                swap_after_mb=swap_after,
                result_dir=result_dir,
                summary=summary,
            )
        )
        if proc.returncode != 0 and args.stop_on_failure:
            break

    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    print(f"[matrix-scale] CSV written: {csv_path}")
    return 0 if all(row["returncode"] == 0 for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
