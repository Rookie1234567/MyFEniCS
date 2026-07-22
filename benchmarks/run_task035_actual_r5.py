from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

from mpi4py import MPI

from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _sample,
    _source_provenance,
    _stage_peaks,
)
from benchmarks.task034_wsl_resources import effective_memory_limit
from src.solvers.solve_vector_maxwell import _json_default


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/task035/actual_global_r5"
GIB = 1024**3


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_from_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _memory_snapshot() -> dict[str, Any]:
    effective = effective_memory_limit()
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "effective_limit": effective,
        "artifact_filesystem_free_bytes": shutil.disk_usage(
            DEFAULT_ARTIFACT_ROOT.parent
        ).free,
    }


def _append_progress(path: Path, stage: str, status: str) -> None:
    if MPI.COMM_WORLD.rank != 0:
        return
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "status": status,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _worker(args: argparse.Namespace) -> int:
    from src.adaptivity.global_two_level_r5 import run_target_global_two_level_r5

    progress_path = args.run_dir / "progress_3d.jsonl"

    def progress(stage: str, status: str) -> None:
        _append_progress(progress_path, stage, status)

    result = run_target_global_two_level_r5(
        args.run_dir,
        coarse_degree=args.coarse_degree,
        enriched_degree=args.enriched_degree,
        h_nm=args.h_nm,
        theta=args.theta,
        polarization_kind=args.polarization_kind,
        progress_observer=progress,
    )
    if MPI.COMM_WORLD.rank == 0:
        (args.run_dir / "actual_r5_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=_json_default)
            + "\n",
            encoding="utf-8",
        )
    MPI.COMM_WORLD.barrier()
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task035 actual global two-level R5 target watchdog."
    )
    parser.add_argument("--coarse-degree", type=int, default=2)
    parser.add_argument("--enriched-degree", type=int, default=3)
    parser.add_argument("--h-nm", type=float, default=10.0)
    parser.add_argument("--theta", type=float, default=0.5)
    parser.add_argument("--polarization-kind", choices=("s", "p"), default="s")
    parser.add_argument("--mpi-size", type=int, default=8)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--warning-gib", type=float)
    parser.add_argument("--terminate-gib", type=float)
    parser.add_argument("--timeout-seconds", type=float, default=7200.0)
    parser.add_argument(
        "--verified-clean-sha",
        default=os.environ.get("TASK035_VERIFIED_CLEAN_SHA"),
    )
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args(argv)
    if args.mpi_size < 1:
        parser.error("--mpi-size must be positive.")
    if args.coarse_degree < 1 or args.enriched_degree <= args.coarse_degree:
        parser.error("require 1 <= coarse-degree < enriched-degree.")
    if args.h_nm <= 0.0:
        parser.error("--h-nm must be positive.")
    if not 0.0 < args.theta <= 1.0:
        parser.error("--theta must lie in (0, 1].")
    if args.poll_interval < 0.05:
        parser.error("--poll-interval must be at least 0.05 seconds.")
    if args.timeout_seconds <= 0.0:
        parser.error("--timeout-seconds must be positive.")
    return args


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=15)


def _sampler_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def maximum(name: str) -> float | None:
        values = [
            float(row[name])
            for row in rows
            if isinstance(row.get(name), (int, float))
        ]
        return max(values) if values else None

    process_tree = maximum("mpi_process_tree_rss_mb")
    process_swap = maximum("mpi_process_tree_swap_mb")
    worker_counts = []
    for row in rows:
        try:
            workers = json.loads(str(row.get("worker_rank_rss_mb_json", "[]")))
        except json.JSONDecodeError:
            continue
        if isinstance(workers, list):
            worker_counts.append(len(workers))
    return {
        "sample_count": len(rows),
        "max_process_tree_rss_mb": process_tree,
        "max_process_tree_swap_mb": process_swap,
        "memory_authority_gib": (
            None if process_tree is None else process_tree / 1024.0
        ),
        "max_observed_worker_rank_count": max(worker_counts, default=0),
        "stage_peaks": _stage_peaks(rows) if rows else [],
    }


def _compact_solve(entry: dict[str, Any]) -> dict[str, Any]:
    summary = entry["summary"]
    return {
        "degree": entry["degree"],
        "h_nm": entry["h_nm"],
        "case_status": summary.get("case_status"),
        "official_result": summary.get("official_result"),
        "mpi_size": summary.get("mpi_size"),
        "num_mesh_cells": summary.get("num_mesh_cells"),
        "num_nedelec_dofs": summary.get("num_nedelec_dofs"),
        "matrix_stats": summary.get("matrix_stats"),
        "linear_system_relative_residual": summary.get(
            "linear_system_relative_residual"
        ),
        "R_total": summary.get("R_total"),
        "T_total": summary.get("T_total"),
        "A_volume_total": summary.get("A_volume_total"),
        "energy_closure_error_port_volume": summary.get(
            "energy_closure_error_port_volume"
        ),
        "floquet_num_constraints": summary.get("floquet_num_constraints"),
        "elapsed_seconds": summary.get("elapsed_seconds"),
    }


def _qualify(
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    authority_readable: bool,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    r5 = result.get("R5") or {}
    energy = r5.get("correction_energy") or {}
    marking = r5.get("marking") or {}
    solves = [result.get("coarse") or {}, result.get("enriched") or {}]
    summaries = [entry.get("summary") or {} for entry in solves]
    checks = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "resource_authority_readable": authority_readable,
        "all_expected_mpi_ranks_observed": (
            sampler.get("max_observed_worker_rank_count") == args.mpi_size
        ),
        "no_process_tree_swap": sampler.get("max_process_tree_swap_mb") == 0.0,
        "result_status": result.get("status") == "actual_global_r5_pass",
        "formal_hierarchical_fe_r5": r5.get("formal_hierarchical_fe_r5") is True,
        "finite_cell_contributions": r5.get("finite_cell_contributions") is True,
        "nonnegative_cell_contributions": (
            r5.get("nonnegative_cell_contributions") is True
        ),
        "positive_correction_energy": (
            isinstance(r5.get("correction_energy_norm"), (int, float))
            and float(r5["correction_energy_norm"]) > 0.0
        ),
        "cell_energy_closure_le_1e-10": (
            isinstance(energy.get("relative_closure_error"), (int, float))
            and float(energy["relative_closure_error"]) <= 1.0e-10
        ),
        "dorfler_target_captured": (
            isinstance(marking.get("captured_fraction"), (int, float))
            and float(marking["captured_fraction"]) >= args.theta
        ),
        "both_official_solves": all(
            summary.get("official_result") is True for summary in summaries
        ),
        "both_true_residuals_le_1e-9": all(
            isinstance(summary.get("linear_system_relative_residual"), (int, float))
            and float(summary["linear_system_relative_residual"]) <= 1.0e-9
            for summary in summaries
        ),
        "ordinary_default_unchanged": result.get("ordinary_default_changed") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _run_parent(args: argparse.Namespace) -> int:
    effective = effective_memory_limit()
    if effective["effective_limit_bytes"] is None:
        raise SystemExit("Task035 effective WSL memory limit is unreadable.")
    if args.warning_gib is None:
        args.warning_gib = float(effective["warning_bytes"]) / GIB
    if args.terminate_gib is None:
        args.terminate_gib = float(effective["termination_bytes"]) / GIB
    if not 0.0 < args.warning_gib < args.terminate_gib:
        raise SystemExit("Require 0 < warning-gib < terminate-gib.")
    source_before = _source_provenance(args)
    preflight = _memory_snapshot()
    free_bytes = preflight["artifact_filesystem_free_bytes"]
    if free_bytes < 10 * GIB:
        raise SystemExit("Task035 actual R5 requires at least 10 GiB free artifact space.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (
        args.run_dir
        or args.artifact_root
        / (
            f"p{args.coarse_degree}_p{args.enriched_degree}_h{args.h_nm:g}_"
            f"pol{args.polarization_kind}_mpi{args.mpi_size}_{timestamp}"
        )
    ).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    args.run_dir = run_dir
    progress_path = run_dir / "progress_3d.jsonl"
    timeline_path = run_dir / "memory_timeline.csv"
    stdout_path = run_dir / "worker_stdout.txt"
    result_path = run_dir / "actual_r5_result.json"
    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task035_actual_r5",
        "--worker",
        "--coarse-degree",
        str(args.coarse_degree),
        "--enriched-degree",
        str(args.enriched_degree),
        "--h-nm",
        str(args.h_nm),
        "--theta",
        str(args.theta),
        "--polarization-kind",
        args.polarization_kind,
        "--run-dir",
        str(run_dir),
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    warning_triggered = False
    terminated_for_memory = False
    terminated_for_timeout = False
    authority_readable = True
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            start_new_session=True,
        )
        previous: dict[str, Any] | None = None
        while True:
            elapsed = time.perf_counter() - started
            row = _sample(process.pid, progress_path, elapsed)
            _add_cpu_core_equivalents(row, previous)
            previous = row
            rows.append(row)
            rss_mb = row.get("mpi_process_tree_rss_mb")
            swap_mb = row.get("mpi_process_tree_swap_mb")
            readable = isinstance(rss_mb, (int, float)) and isinstance(
                swap_mb, (int, float)
            )
            authority_readable &= readable
            rss_gib = None if not readable else float(rss_mb) / 1024.0
            if rss_gib is not None:
                warning_triggered |= rss_gib >= args.warning_gib
            if process.poll() is None and not readable:
                _terminate_process_group(process)
            elif (
                process.poll() is None
                and rss_gib is not None
                and rss_gib >= args.terminate_gib
            ):
                terminated_for_memory = True
                _terminate_process_group(process)
            elif process.poll() is None and elapsed >= args.timeout_seconds:
                terminated_for_timeout = True
                _terminate_process_group(process)
            if process.poll() is not None:
                break
            time.sleep(args.poll_interval)
        return_code = int(process.returncode or 0)

    with timeline_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    result = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.is_file()
        else {}
    )
    sampler = _sampler_summary(rows)
    qualification = _qualify(
        result,
        args=args,
        return_code=return_code,
        terminated_for_memory=terminated_for_memory,
        terminated_for_timeout=terminated_for_timeout,
        authority_readable=authority_readable,
        sampler=sampler,
    )
    head_after = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    status_after = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).strip()
    source_stable = head_after == source_before["commit_sha"] and not status_after
    qualification["checks"]["source_stable_and_clean_after"] = source_stable
    if not source_stable:
        qualification["failures"].append("source_stable_and_clean_after")
        qualification["pass"] = False
    status = "actual_global_r5_pass" if qualification["pass"] else "formal_not_pass"
    record = {
        "schema_version": "task035.actual-global-r5-watchdog.v1",
        "benchmark_id": "task035_target_actual_global_r5",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "command": command,
        "source": {
            **source_before,
            "head_after_sha": head_after,
            "status_after_before_record_write": status_after,
            "stable_and_clean_after": source_stable,
        },
        "resource_preflight": preflight,
        "resource_policy": {
            "one_heavy_case_at_a_time": True,
            "warning_gib": args.warning_gib,
            "termination_gib": args.terminate_gib,
            "timeout_seconds": args.timeout_seconds,
            "swap_allowed": False,
            "termination_scope": "complete_process_group",
        },
        "resource_authority": sampler,
        "warning_triggered": warning_triggered,
        "terminated_for_memory": terminated_for_memory,
        "terminated_for_timeout": terminated_for_timeout,
        "qualification": qualification,
        "target_identity": result.get("target_identity"),
        "coarse": _compact_solve(result["coarse"]) if result else None,
        "enriched": _compact_solve(result["enriched"]) if result else None,
        "official_observable_delta_l2": result.get(
            "official_observable_delta_l2"
        ),
        "R5": result.get("R5"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "raw_evidence": {
            "run_directory": _path_from_root(run_dir),
            "actual_r5_result": _path_from_root(result_path),
            "actual_r5_result_sha256": _sha256(result_path),
            "memory_timeline": _path_from_root(timeline_path),
            "memory_timeline_sha256": _sha256(timeline_path),
            "progress": _path_from_root(progress_path),
            "progress_sha256": _sha256(progress_path),
            "stdout": _path_from_root(stdout_path),
            "stdout_sha256": _sha256(stdout_path),
        },
    }
    record_path = args.record or (run_dir / "watchdog_summary.json")
    if not record_path.is_absolute():
        record_path = ROOT / record_path
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, default=_json_default)
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": status,
                "memory_authority_gib": sampler["memory_authority_gib"],
                "record": _path_from_root(record_path),
                "failures": qualification["failures"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if qualification["pass"] else 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.worker:
        if args.run_dir is None:
            raise SystemExit("--worker requires --run-dir.")
        return _worker(args)
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
