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


MB_PER_GB = 1024.0
BYTES_PER_GB = 1024.0**3


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
        matches = re.findall(r"3D case output directory:\s*(.+)", stdout)
    if not matches:
        return None
    return Path(matches[-1].strip())


def _load_last_progress(result_dir: Path | None) -> dict[str, Any] | None:
    if result_dir is None:
        return None
    path = result_dir / "progress_3d.jsonl"
    if not path.exists():
        return None
    last = None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    return last


def _value(summary: dict[str, Any] | None, key: str, default=None):
    if summary is None:
        return default
    return summary.get(key, default)


def _mb_to_gb(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / MB_PER_GB
    except (TypeError, ValueError):
        return None


def _bytes_to_gb(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / BYTES_PER_GB
    except (TypeError, ValueError):
        return None


def _mesh_cell_count(mesh_cells: Any) -> int | None:
    if not isinstance(mesh_cells, (list, tuple)) or not mesh_cells:
        return None
    total = 1
    try:
        for value in mesh_cells:
            total *= int(value)
    except (TypeError, ValueError):
        return None
    return total


def _tail_text(text: str, *, max_lines: int = 20, max_chars: int = 6000) -> str:
    lines = text.splitlines()
    tail = "\n".join(lines[-max_lines:])
    if len(tail) > max_chars:
        return tail[-max_chars:]
    return tail


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


def _case_status(returncode: int, timed_out: bool, summary_case_status: Any = None) -> str:
    if timed_out:
        return "timeout"
    if isinstance(summary_case_status, str) and summary_case_status.startswith("failed"):
        return "failed"
    if returncode == 0:
        return "completed"
    if returncode in {137, -9}:
        return "killed"
    return "failed"


def _matrix_value(summary: dict[str, Any] | None, key: str, last_progress: dict[str, Any] | None = None):
    stats = _value(summary, "matrix_stats", {}) or {}
    value = stats.get(key)
    if value is not None:
        return value
    if last_progress is None:
        return None
    return last_progress.get(key)


def _config_value(summary: dict[str, Any] | None, key: str, default=None):
    config = _value(summary, "config", {}) or {}
    return config.get(key, default)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    nedelec_degree: int,
    solver_profile: str,
    returncode: int,
    timed_out: bool,
    elapsed_wall_seconds: float,
    swap_before_mb: float | None,
    swap_after_mb: float | None,
    result_dir: Path | None,
    summary: dict[str, Any] | None,
    last_progress: dict[str, Any] | None,
    stdout_file: Path | None,
    stderr_file: Path | None,
    progress_file: Path | None,
    stdout_text: str,
    stderr_text: str,
) -> dict[str, Any]:
    error = _value(summary, "direct_solve_exception", {}) or {}
    ooc_runtime = _value(summary, "mumps_ooc_runtime", {}) or {}
    matrix_memory_mb = _matrix_value(summary, "matrix_memory_mb", last_progress)
    estimated_aij_mb = _matrix_value(summary, "matrix_memory_estimate_mb", last_progress)
    peak_rss_mb = _value(summary, "max_rss_mb")
    if peak_rss_mb is None and last_progress is not None:
        peak_rss_mb = last_progress.get("max_rss_mb")
    matrix_memory_gb = _mb_to_gb(matrix_memory_mb)
    estimated_aij_gb = _mb_to_gb(estimated_aij_mb)
    peak_rss_gb = _mb_to_gb(peak_rss_mb)
    total_rss_upper_gb = None if peak_rss_gb is None else peak_rss_gb * float(mpi_procs)
    ooc_removed_gb = _bytes_to_gb(ooc_runtime.get("mumps_ooc_cleanup_removed_file_bytes"))
    ooc_residual_gb = _bytes_to_gb(ooc_runtime.get("mumps_ooc_residual_file_bytes"))
    ooc_disk_gb = max(value for value in (ooc_removed_gb or 0.0, ooc_residual_gb or 0.0))
    swap_before_gb = _mb_to_gb(swap_before_mb)
    swap_after_gb = _mb_to_gb(swap_after_mb)
    swap_delta_gb = None if swap_before_mb is None or swap_after_mb is None else (swap_after_mb - swap_before_mb) / MB_PER_GB
    effective_lu_proxy_gb = (
        None
        if total_rss_upper_gb is None or estimated_aij_gb is None
        else total_rss_upper_gb - estimated_aij_gb
    )
    rss_to_matrix_ratio = (
        None
        if total_rss_upper_gb is None or estimated_aij_gb in {None, 0.0}
        else total_rss_upper_gb / estimated_aij_gb
    )
    mesh_cells_resolved = _value(summary, "mesh_cells_resolved")
    summary_case_status = _value(summary, "case_status")
    air_height = _as_float(_config_value(summary, "air_height"))
    substrate_thickness = _as_float(_config_value(summary, "substrate_thickness"))
    grating_height = _as_float(_config_value(summary, "grating_height"))
    physical_z_min = _as_float(_config_value(summary, "physical_z_min"))
    physical_z_max = _as_float(_config_value(summary, "physical_z_max"))
    R_total = _as_float(_value(summary, "R_total"))
    T_total = _as_float(_value(summary, "T_total"))
    A_volume_total = _as_float(_value(summary, "A_volume_total"))
    R_plus_T = _as_float(_value(summary, "R_plus_T"))
    R_plus_T_plus_A_volume = (
        None
        if R_total is None or T_total is None or A_volume_total is None
        else float(R_total + T_total + A_volume_total)
    )
    return {
        "domain_height_nm": None
        if physical_z_min is None or physical_z_max is None
        else float(physical_z_max - physical_z_min),
        "substrate_thickness_nm": substrate_thickness,
        "top_air_above_grating_nm": None
        if air_height is None or grating_height is None
        else float(air_height - grating_height),
        "air_height_parameter_nm": air_height,
        "grating_height_nm": grating_height,
        "period_x_nm": _config_value(summary, "period_x"),
        "period_y_nm": _config_value(summary, "period_y"),
        "h_nm": mesh_target_size,
        "p": nedelec_degree,
        "mpi_ranks": mpi_procs,
        "mesh_target_size_nm": mesh_target_size,
        "mpi_procs": mpi_procs,
        "solver_profile": solver_profile,
        "returncode": returncode,
        "status": _case_status(returncode, timed_out, summary_case_status),
        "case_status": summary_case_status,
        "result_dir": "" if result_dir is None else str(result_dir),
        "stdout_file": "" if stdout_file is None else str(stdout_file),
        "stderr_file": "" if stderr_file is None else str(stderr_file),
        "progress_file": "" if progress_file is None else str(progress_file),
        "last_progress_stage": None if last_progress is None else last_progress.get("stage"),
        "last_progress_status": None if last_progress is None else last_progress.get("status"),
        "failure_stage": _value(summary, "failure_stage"),
        "petsc_error_code": error.get("petsc_error_code"),
        "petsc_error_type": error.get("petsc_error_type"),
        "mumps_infog_1": error.get("mumps_infog_1"),
        "mumps_infog_2": error.get("mumps_infog_2"),
        "mumps_ooc_tmpdir": ooc_runtime.get("mumps_ooc_tmpdir"),
        "mumps_ooc_cleaned_by_solver": ooc_runtime.get("mumps_ooc_cleaned_by_solver"),
        "mumps_ooc_cleanup_attempted": ooc_runtime.get("mumps_ooc_cleanup_attempted"),
        "mumps_ooc_cleanup_success": ooc_runtime.get("mumps_ooc_cleanup_success"),
        "mumps_ooc_cleanup_removed_file_count": ooc_runtime.get("mumps_ooc_cleanup_removed_file_count"),
        "mumps_ooc_cleanup_removed_file_bytes": ooc_runtime.get("mumps_ooc_cleanup_removed_file_bytes"),
        "mumps_ooc_cleanup_removed_file_GB": ooc_removed_gb,
        "mumps_ooc_retained_on_failure": ooc_runtime.get("mumps_ooc_retained_on_failure"),
        "mumps_ooc_residual_file_count": ooc_runtime.get("mumps_ooc_residual_file_count"),
        "mumps_ooc_residual_file_bytes": ooc_runtime.get("mumps_ooc_residual_file_bytes"),
        "mumps_ooc_residual_file_GB": ooc_residual_gb,
        "ooc_disk_GB": ooc_disk_gb,
        "mesh_cells_resolved": mesh_cells_resolved,
        "cells": _mesh_cell_count(mesh_cells_resolved),
        "N1curl_raw_dofs": _value(
            summary,
            "num_nedelec_dofs",
            None if last_progress is None else last_progress.get("dofs"),
        ),
        "dof_raw_nedelec": _value(
            summary,
            "num_nedelec_dofs",
            None if last_progress is None else last_progress.get("dofs"),
        ),
        "floquet_constraints": _value(
            summary,
            "floquet_num_constraints",
            None if last_progress is None else last_progress.get("floquet_constraints"),
        ),
        "constrained_system_size": _value(summary, "constrained_linear_system_size"),
        "dtn_auxiliary_dofs": _value(summary, "stage4_dtn_num_auxiliary_dofs"),
        "system_rows": _matrix_value(summary, "matrix_rows", last_progress),
        "system_cols": _matrix_value(summary, "matrix_cols", last_progress),
        "matrix_rows": _matrix_value(summary, "matrix_rows", last_progress),
        "matrix_cols": _matrix_value(summary, "matrix_cols", last_progress),
        "nnz_used": _matrix_value(summary, "matrix_nnz_used", last_progress),
        "nnz_allocated": _matrix_value(summary, "matrix_nnz_allocated", last_progress),
        "avg_nnz_per_row": _matrix_value(summary, "matrix_average_nnz_per_row", last_progress),
        "average_nnz_per_row": _matrix_value(summary, "matrix_average_nnz_per_row", last_progress),
        "average_allocated_nnz_per_row": _matrix_value(
            summary,
            "matrix_average_allocated_nnz_per_row",
            last_progress,
        ),
        "petsc_matrix_memory_mb": matrix_memory_mb,
        "estimated_aij_matrix_memory_mb": estimated_aij_mb,
        "matrix_memory_GB": matrix_memory_gb,
        "PETSc_matrix_memory_GB": matrix_memory_gb,
        "estimated_AIJ_matrix_memory_GB": estimated_aij_gb,
        "solve_time_seconds": _timing_value(
            summary,
            "linear_problem_solve",
            "stage4_dtn_linear_solve_seconds",
            "stage4_dtn_port_assembly_and_solve",
        ),
        "solve_time_s": _timing_value(
            summary,
            "linear_problem_solve",
            "stage4_dtn_linear_solve_seconds",
            "stage4_dtn_port_assembly_and_solve",
        ),
        "elapsed_wall_seconds": elapsed_wall_seconds,
        "elapsed_wall_s": elapsed_wall_seconds,
        "assemble_elapsed_s": elapsed_wall_seconds,
        "summary_elapsed_seconds": _value(summary, "elapsed_seconds"),
        "peak_rss_mb": peak_rss_mb,
        "peak_RSS_per_rank_max_GB": peak_rss_gb,
        "rss_rank_max_mb": peak_rss_mb,
        "rss_rank_sum_mb": None if total_rss_upper_gb is None else total_rss_upper_gb * MB_PER_GB,
        "rss_rank_sum_GB": total_rss_upper_gb,
        "rss_rank_mean_mb": None,
        "rss_rank_min_mb": None,
        "rss_rank_imbalance": None,
        "rss_rank_statistics_source": "upper_bound_from_global_max_times_ranks",
        "estimated_total_RSS_upper_GB": total_rss_upper_gb,
        "swap_used_before_mb": swap_before_mb,
        "swap_used_after_mb": swap_after_mb,
        "swap_used_delta_mb": None if swap_before_mb is None or swap_after_mb is None else swap_after_mb - swap_before_mb,
        "swap_before_GB": swap_before_gb,
        "swap_after_GB": swap_after_gb,
        "swap_delta_GB": swap_delta_gb,
        "effective_LU_memory_proxy_GB": effective_lu_proxy_gb,
        "rss_to_matrix_ratio": rss_to_matrix_ratio,
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
        "R_total": R_total,
        "T_total": T_total,
        "A_volume_total": A_volume_total,
        "R_plus_T": R_plus_T,
        "R_plus_T_plus_A_volume": R_plus_T_plus_A_volume,
        "energy_closure_error_port_volume": _value(summary, "energy_closure_error_port_volume"),
        "A_port_balance_minus_A_volume_total": _value(summary, "A_port_balance_minus_A_volume_total"),
        "num_reflection_orders": _value(summary, "dtn_port_top_mode_count"),
        "num_transmission_orders": _value(summary, "dtn_port_bottom_mode_count"),
        "dtn_port_propagating_mode_count": _value(summary, "dtn_port_propagating_mode_count"),
        "stdout_tail": _tail_text(stdout_text),
        "stderr_tail": _tail_text(stderr_text),
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
        args.stage4_dtn_assembly,
        "--petsc-direct-solver-profile",
        args.current_solver_profile,
    ]
    optional_runner_args = {
        "--period-x": args.period_x,
        "--period-y": args.period_y,
        "--air-height": args.air_height,
        "--substrate-thickness": args.substrate_thickness,
        "--grating-width-x": args.grating_width_x,
        "--grating-width-y": args.grating_width_y,
        "--grating-height": args.grating_height,
        "--lambda0": args.lambda0,
        "--n-substrate": args.n_substrate,
        "--n-grating": args.n_grating,
        "--polarization-kind": args.polarization_kind,
        "--mesh-cell-type": args.mesh_cell_type,
        "--mesh-spacing-mode": args.mesh_spacing_mode,
    }
    for option, value in optional_runner_args.items():
        if value is not None:
            command.extend([option, str(value)])
    if args.matrix_diagnostics_assemble_unconstrained:
        command.append("--matrix-diagnostics-assemble-unconstrained")
    if args.assemble_only:
        command.append("--matrix-diagnostics-assemble-only")
    for option in args.extra_runner_arg:
        command.extend(option.split())
    for option in args.petsc_option:
        if option.startswith("-"):
            command.append(option)
        else:
            command.extend(["--petsc-extra-option", option])
    if args.current_mpi_procs > 1:
        command = ["mpiexec", "-n", str(args.current_mpi_procs), *command]
    return command


def _write_rows_csv(csv_path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run 3D Maxwell matrix/solver scaling diagnostics and write CSV.")
    parser.add_argument("--mesh-sizes", type=float, nargs="+", default=[20.0, 15.0, 12.0, 10.0, 8.0])
    parser.add_argument("--mpi-procs", type=int, default=1)
    parser.add_argument("--mpi-procs-list", type=int, nargs="+", default=None)
    parser.add_argument("--stage-case", default="stage4_block_grating")
    parser.add_argument("--case", default="normal")
    parser.add_argument("--nedelec-degree", type=int, default=1)
    parser.add_argument("--visualization-degree", type=int, default=1)
    parser.add_argument("--stage4-boundary-model", default="dtn_port")
    parser.add_argument("--stage4-dtn-order-policy", default="zero_order")
    parser.add_argument("--stage4-dtn-assembly", default="auxiliary")
    parser.add_argument("--period-x", type=float, default=None)
    parser.add_argument("--period-y", type=float, default=None)
    parser.add_argument("--air-height", type=float, default=None)
    parser.add_argument("--substrate-thickness", type=float, default=None)
    parser.add_argument("--grating-width-x", type=float, default=None)
    parser.add_argument("--grating-width-y", type=float, default=None)
    parser.add_argument("--grating-height", type=float, default=None)
    parser.add_argument("--lambda0", type=float, default=None)
    parser.add_argument("--n-substrate", default=None)
    parser.add_argument("--n-grating", default=None)
    parser.add_argument("--polarization-kind", default=None)
    parser.add_argument("--mesh-cell-type", default=None)
    parser.add_argument("--mesh-spacing-mode", default=None)
    parser.add_argument(
        "--petsc-direct-solver-profile",
        choices=("default", "mumps_ooc"),
        default="default",
    )
    parser.add_argument(
        "--solver-profiles",
        nargs="+",
        choices=("default", "mumps_ooc"),
        default=None,
    )
    parser.add_argument("--matrix-diagnostics-assemble-unconstrained", action="store_true")
    parser.add_argument("--assemble-only", action="store_true")
    parser.add_argument("--petsc-option", action="append", default=[])
    parser.add_argument("--extra-runner-arg", action="append", default=[])
    parser.add_argument("--output-csv", default=None)
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument(
        "--case-timeout-seconds",
        type=float,
        default=None,
        help="Optional timeout for each subprocess case. Timed-out cases are recorded and the sweep continues/stops according to --stop-on-failure.",
    )
    args = parser.parse_args(argv)

    root = project_root()
    out_dir = root / "results" / f"matrix_scale_{_timestamp()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = Path(args.output_csv) if args.output_csv else out_dir / "matrix_scale.csv"
    rows: list[dict[str, Any]] = []
    mpi_procs_list = args.mpi_procs_list or [args.mpi_procs]
    solver_profiles = args.solver_profiles or [args.petsc_direct_solver_profile]
    for mpi_procs in mpi_procs_list:
        for solver_profile in solver_profiles:
            args.current_mpi_procs = mpi_procs
            args.current_solver_profile = solver_profile
            for mesh_size in args.mesh_sizes:
                command = _command_for_case(args, mesh_size)
                label = f"h={mesh_size:g}, np={mpi_procs}, solver={solver_profile}"
                print(f"[matrix-scale] running {label}")
                print("[matrix-scale] command:", " ".join(command))
                swap_before = _swap_used_mb()
                t0 = time.perf_counter()
                timed_out = False
                try:
                    proc = subprocess.run(
                        command,
                        cwd=root,
                        text=True,
                        capture_output=True,
                        timeout=args.case_timeout_seconds,
                    )
                    returncode = proc.returncode
                    stdout_text = proc.stdout
                    stderr_text = proc.stderr
                except subprocess.TimeoutExpired as exc:
                    timed_out = True
                    returncode = 124
                    stdout_text = _coerce_text(exc.stdout)
                    stderr_text = _coerce_text(exc.stderr)
                    stderr_text += f"\n[matrix-scale] timeout after {args.case_timeout_seconds} seconds\n"
                elapsed = time.perf_counter() - t0
                swap_after = _swap_used_mb()
                result_dir = _extract_result_dir(stdout_text)
                summary = _load_summary(result_dir) if result_dir is not None else None
                last_progress = _load_last_progress(result_dir)
                file_tag = f"run_np{mpi_procs}_{solver_profile}_h{str(mesh_size).replace('.', 'p')}"
                stdout_file = out_dir / f"{file_tag}_stdout.txt"
                stderr_file = out_dir / f"{file_tag}_stderr.txt"
                stdout_file.write_text(stdout_text, encoding="utf-8")
                stderr_file.write_text(stderr_text, encoding="utf-8")
                progress_file = result_dir / "progress_3d.jsonl" if result_dir is not None else None
                row = _row_from_result(
                    mesh_target_size=mesh_size,
                    mpi_procs=mpi_procs,
                    nedelec_degree=args.nedelec_degree,
                    solver_profile=solver_profile,
                    returncode=returncode,
                    timed_out=timed_out,
                    elapsed_wall_seconds=elapsed,
                    swap_before_mb=swap_before,
                    swap_after_mb=swap_after,
                    result_dir=result_dir,
                    summary=summary,
                    last_progress=last_progress,
                    stdout_file=stdout_file,
                    stderr_file=stderr_file,
                    progress_file=progress_file if progress_file is not None and progress_file.exists() else None,
                    stdout_text=stdout_text,
                    stderr_text=stderr_text,
                )
                row_json = out_dir / f"{file_tag}_row.json"
                row_json.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
                rows.append(row)
                _write_rows_csv(csv_path, rows)
                if returncode != 0 and args.stop_on_failure:
                    break
            if rows and rows[-1]["returncode"] != 0 and args.stop_on_failure:
                break
        if rows and rows[-1]["returncode"] != 0 and args.stop_on_failure:
            break

    _write_rows_csv(csv_path, rows)
    print(f"[matrix-scale] CSV written: {csv_path}")
    return 0 if all(row["returncode"] == 0 for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
