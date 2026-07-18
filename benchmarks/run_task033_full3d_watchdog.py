from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.task034_wsl_resources import (
    cgroup_snapshot,
    effective_memory_limit,
    vmstat_swap_pages,
)
from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _historical_peak_upper_bound,
    _read_progress_events,
    _sample,
    _source_provenance,
    _stage_peaks,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = (
    ROOT / "benchmarks" / "artifacts" / "cases" / "091" / "task033_full3d"
)
REFERENCE_PLANES_NM = (10.0, 30.0, 60.0, 90.0, 110.0)
GIB = 1024**3


def _read_int_or_max(path: Path) -> tuple[int | None, str]:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None, "unreadable"
    if text == "max":
        return None, "unbounded"
    try:
        return int(text), "finite"
    except ValueError:
        return None, "unreadable"


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _host_available_bytes() -> int | None:
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("MemAvailable:"):
            try:
                return int(line.split()[1]) * 1024
            except (IndexError, ValueError):
                return None
    return None


def _resource_snapshot() -> dict[str, Any]:
    cgroup = cgroup_snapshot()
    memory = effective_memory_limit()
    swap = vmstat_swap_pages()
    memory_max = cgroup.get("memory_limit_bytes")
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cgroup_path": cgroup.get("path"),
        "cgroup_is_dedicated_job_authority": cgroup.get(
            "dedicated_job_cgroup", False
        ),
        "cgroup_memory_max_bytes": memory_max,
        "cgroup_memory_max_state": (
            "finite" if isinstance(memory_max, int) else "unbounded_or_unreadable"
        ),
        "cgroup_swap_max_bytes": None,
        "cgroup_swap_max_state": "not_used_as_limit",
        "cgroup_memory_current_bytes": cgroup.get("memory_current_bytes"),
        "cgroup_swap_current_bytes": cgroup.get("swap_current_bytes"),
        "host_available_bytes": memory.get("mem_available_bytes"),
        "wsl_total_bytes": memory.get("mem_total_bytes"),
        "task034_effective_limit": memory,
        "wsl_vm_global_swap_diagnostic": swap,
    }


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _path_from_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _full3d_config(args: argparse.Namespace):
    from src.common.config_3d import target_stage4_config

    cfg = target_stage4_config(degree=args.degree, h_nm=args.h_nm)
    full_solve = args.run_kind == "full-solve"
    factorization_only = args.run_kind == "factorization-only"
    return replace(
        cfg,
        petsc_direct_solver_profile=args.profile,
        matrix_diagnostics_assemble_only=args.run_kind == "assembly-only",
        matrix_diagnostics_factorization_only=factorization_only,
        full3d_reference_export=full_solve,
        full3d_reference_plane_z=REFERENCE_PLANES_NM if full_solve else (),
        full3d_reference_sample_count_x=40,
        full3d_reference_sample_count_y=20,
        unique_output=False,
    )


def _worker(args: argparse.Namespace) -> int:
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    run_stage4b_block_grating_3d_case(_full3d_config(args), args.run_dir)
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Task33 p3/p4 target full3D assembly calibration and controlled "
            "direct-reference watchdog."
        )
    )
    parser.add_argument("--degree", type=int, choices=(3, 4), required=True)
    parser.add_argument(
        "--h-nm", type=float, choices=(10.0, 7.5, 5.0, 3.0), default=5.0
    )
    parser.add_argument(
        "--run-kind",
        choices=("assembly-only", "factorization-only", "full-solve"),
        default="assembly-only",
    )
    parser.add_argument("--mpi-size", type=int, default=4)
    parser.add_argument(
        "--profile",
        choices=("default", "mumps_ooc", "mumps_blr"),
        default="default",
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--warning-gib", type=float)
    parser.add_argument("--terminate-gib", type=float)
    parser.add_argument("--timeout-seconds", type=float, default=7200.0)
    parser.add_argument(
        "--allow-swap",
        action="store_true",
        help=(
            "Permit a full solve to use cgroup swap. The combined memory+swap "
            "authority remains bounded by --terminate-gib."
        ),
    )
    parser.add_argument(
        "--p3-gate-record",
        type=Path,
        help=(
            "Required for degree 4. Must prove a successful p3/h5 full solve "
            "with zero swap and memory authority below 10 GiB."
        ),
    )
    parser.add_argument(
        "--p4-trace-record",
        type=Path,
        help=(
            "Required for degree 4. Must be the passing MPI1/MPI4 p4 "
            "four-mode matched-trace aggregate."
        ),
    )
    parser.add_argument(
        "--verified-clean-sha",
        default=os.environ.get("TASK033_VERIFIED_CLEAN_SHA"),
    )
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args(argv)
    if args.h_nm == 3.0 and args.degree != 3:
        parser.error("Task034 h=3 nm full3D is restricted to degree 3.")
    return args


def _validate_p4_gate(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.degree != 4:
        return None
    if args.p3_gate_record is None:
        raise SystemExit("p4 is locked: --p3-gate-record is required.")
    if args.p4_trace_record is None:
        raise SystemExit("p4 is locked: --p4-trace-record is required.")
    path = (
        args.p3_gate_record
        if args.p3_gate_record.is_absolute()
        else ROOT / args.p3_gate_record
    )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"p4 is locked: cannot read p3 gate record: {exc}") from exc
    resource = record.get("resource_authority") or {}
    checks = {
        "p3_degree": record.get("degree") == 3,
        "same_h": float(record.get("h_nm", -1.0)) == args.h_nm,
        "full_solve": record.get("run_kind") == "full-solve",
        "reference_pass": record.get("status") == "full3d_reference_pass",
        "no_swap": record.get("no_swap") is True,
        "memory_below_10_gib": (
            isinstance(resource.get("memory_authority_gib"), (int, float))
            and float(resource["memory_authority_gib"]) < 10.0
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise SystemExit(f"p4 is locked; failed p3 gates: {failures}")
    trace_path = (
        args.p4_trace_record
        if args.p4_trace_record.is_absolute()
        else ROOT / args.p4_trace_record
    )
    try:
        trace_record = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"p4 is locked: cannot read four-mode trace record: {exc}"
        ) from exc
    trace_gates = trace_record.get("gates") or {}
    trace_checks = {
        "record_type": (
            trace_record.get("record_type")
            == "p4_four_mode_matched_trace_aggregate"
        ),
        "status": (
            trace_record.get("status") == "p4_four_mode_matched_trace_pass"
        ),
        "four_mode_trace_pass": (
            trace_gates.get("p4_four_mode_matched_trace") is True
        ),
        "mpi_identity_pass": (
            trace_gates.get("mpi1_mpi4_compact_identity") is True
        ),
        "same_current_source": (
            trace_record.get("source_commit_sha") == args.verified_clean_sha
        ),
    }
    trace_failures = [
        name for name, passed in trace_checks.items() if not passed
    ]
    if trace_failures:
        raise SystemExit(
            f"p4 is locked; failed four-mode trace gates: {trace_failures}"
        )
    return {
        "p3": {
            "path": _path_from_root(path),
            "sha256": _sha256(path),
            "checks": checks,
        },
        "p4_four_mode_trace": {
            "path": _path_from_root(trace_path),
            "sha256": _sha256(trace_path),
            "checks": trace_checks,
        },
        "pass": True,
    }


def _sampler_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def maximum(name: str) -> float | None:
        values = [
            float(row[name])
            for row in rows
            if isinstance(row.get(name), (int, float))
        ]
        return max(values) if values else None

    def delta(name: str) -> int | None:
        values = [
            int(row[name])
            for row in rows
            if isinstance(row.get(name), (int, float))
        ]
        return max(values) - min(values) if values else None

    worker_mb = maximum("worker_rank_rss_sum_mb")
    process_tree_mb = maximum("mpi_process_tree_rss_mb")
    process_tree_swap_mb = maximum("mpi_process_tree_swap_mb")
    dedicated_rows = [row for row in rows if row.get("job_cgroup_dedicated") is True]
    dedicated_cgroup_values = [
        float(row["container_cgroup_current_mb"])
        for row in dedicated_rows
        if isinstance(row.get("container_cgroup_current_mb"), (int, float))
    ]
    dedicated_swap_values = [
        float(row["container_swap_current_mb"])
        for row in dedicated_rows
        if isinstance(row.get("container_swap_current_mb"), (int, float))
    ]
    cgroup_mb = max(dedicated_cgroup_values) if dedicated_cgroup_values else None
    swap_mb = max(dedicated_swap_values) if dedicated_swap_values else None
    memory_authority_mb = (
        None
        if process_tree_mb is None
        else max(process_tree_mb, float(cgroup_mb or 0.0))
    )
    combined_authority_mb = memory_authority_mb
    worker_rank_counts: list[int] = []
    for row in rows:
        try:
            workers = json.loads(str(row.get("worker_rank_rss_mb_json", "[]")))
        except json.JSONDecodeError:
            continue
        if isinstance(workers, list):
            worker_rank_counts.append(len(workers))
    return {
        "poll_interval_seconds": None,
        "sample_count": len(rows),
        "max_simultaneous_worker_rss_mb": worker_mb,
        "max_process_tree_rss_mb": process_tree_mb,
        "max_process_tree_swap_mb": process_tree_swap_mb,
        "dedicated_job_cgroup_observed": bool(dedicated_rows),
        "max_container_cgroup_current_mb": cgroup_mb,
        "max_container_swap_current_mb": swap_mb,
        "memory_authority_mb": memory_authority_mb,
        "memory_authority_gib": (
            None if memory_authority_mb is None else memory_authority_mb / 1024.0
        ),
        "combined_memory_swap_authority_mb": combined_authority_mb,
        "combined_memory_swap_authority_gib": (
            None
            if combined_authority_mb is None
            else combined_authority_mb / 1024.0
        ),
        "max_observed_worker_rank_count": (
            max(worker_rank_counts) if worker_rank_counts else 0
        ),
        "pswpin_delta_pages": delta("wsl_pswpin_pages"),
        "pswpout_delta_pages": delta("wsl_pswpout_pages"),
        "stage_peaks": _stage_peaks(rows) if rows else [],
    }


def _factorization_stage_seen(events: list[dict[str, Any]]) -> bool:
    return any(
        str(event.get("stage"))
        in {
            "before_ksp_setup",
            "after_ksp_setup_factorized",
            "before_ksp_solve",
            "after_ksp_solve",
        }
        for event in events
    )


def _solve_stage_seen(events: list[dict[str, Any]]) -> bool:
    return any(
        str(event.get("stage"))
        in {
            "stage4_dtn_augmented_solve",
            "before_ksp_solve",
            "during_ksp_solve_peak",
            "after_ksp_solve",
        }
        for event in events
    )


def _qualify(
    *,
    args: argparse.Namespace,
    solver_summary: dict[str, Any],
    events: list[dict[str, Any]],
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    terminated_for_authority_unreadable: bool,
    no_swap: bool,
    observed_worker_rank_count: int | None = None,
) -> dict[str, Any]:
    matrix = solver_summary.get("matrix_stats") or {}
    common = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "live_authority_readable": not terminated_for_authority_unreadable,
        "all_expected_mpi_ranks_observed": (
            observed_worker_rank_count is None
            or observed_worker_rank_count == args.mpi_size
        ),
        "exact_positive_rows": (
            isinstance(matrix.get("matrix_rows"), (int, float))
            and float(matrix["matrix_rows"]) > 0.0
        ),
        "exact_positive_assembled_nnz": (
            isinstance(matrix.get("matrix_nnz_used"), (int, float))
            and float(matrix["matrix_nnz_used"]) > 0.0
        ),
    }
    if args.run_kind == "assembly-only":
        checks = {
            **common,
            "diagnostic_assemble_only_status": (
                solver_summary.get("case_status") == "diagnostic_assemble_only"
            ),
            "assemble_only_flag": (
                solver_summary.get("matrix_diagnostics_assemble_only") is True
            ),
            "no_factorization_or_solve_stage": not _factorization_stage_seen(events),
            "ksp_iterations_zero": solver_summary.get("ksp_iterations") == 0,
            "no_swap": no_swap,
        }
    elif args.run_kind == "factorization-only":
        factor_inventory = solver_summary.get("stage4_dtn_factor_inventory")
        checks = {
            **common,
            "diagnostic_factorization_only_status": (
                solver_summary.get("case_status")
                == "diagnostic_factorization_only"
            ),
            "assemble_only_false": (
                solver_summary.get("matrix_diagnostics_assemble_only") is False
            ),
            "factorization_only_flag": (
                solver_summary.get("matrix_diagnostics_factorization_only")
                is True
            ),
            "factorization_stage_seen": _factorization_stage_seen(events),
            "solve_stage_not_seen": not _solve_stage_seen(events),
            "factor_inventory_recorded": isinstance(
                factor_inventory, dict
            ),
            "ksp_iterations_zero": solver_summary.get("ksp_iterations") == 0,
            "official_result_false": solver_summary.get("official_result") is False,
            "no_swap": no_swap,
        }
    else:
        residual = solver_summary.get("linear_system_relative_residual")
        checks = {
            **common,
            "completed_status": solver_summary.get("case_status") == "completed",
            "official_result": solver_summary.get("official_result") is True,
            "assemble_only_false": (
                solver_summary.get("matrix_diagnostics_assemble_only") is False
            ),
            "factorization_only_false": (
                solver_summary.get("matrix_diagnostics_factorization_only")
                is False
            ),
            "ksp_converged": solver_summary.get("ksp_converged") is True,
            "true_residual_le_1e-9": (
                isinstance(residual, (int, float)) and float(residual) <= 1.0e-9
            ),
            "reference_exported": (
                solver_summary.get("full3d_reference_exported") is True
            ),
            "swap_policy_satisfied": args.allow_swap or no_swap,
        }
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _terminate(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _run_parent(args: argparse.Namespace) -> int:
    if args.mpi_size < 1:
        raise SystemExit("--mpi-size must be positive.")
    if args.poll_interval < 0.05:
        raise SystemExit("--poll-interval must be at least 0.05 seconds.")
    effective = effective_memory_limit()
    if effective["effective_limit_bytes"] is None:
        raise SystemExit("Task034 effective WSL memory limit is unreadable.")
    if args.warning_gib is None:
        args.warning_gib = float(effective["warning_bytes"]) / GIB
    if args.terminate_gib is None:
        args.terminate_gib = float(effective["termination_bytes"]) / GIB
    if args.warning_gib <= 0 or args.terminate_gib <= args.warning_gib:
        raise SystemExit("Require 0 < warning-gib < terminate-gib.")
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be positive.")
    if args.run_kind != "full-solve" and args.allow_swap:
        raise SystemExit(
            "assembly-only and factorization-only calibration forbid --allow-swap."
        )
    p4_gate = _validate_p4_gate(args)
    source_before = _source_provenance(args)
    environment_before = _resource_snapshot()
    if environment_before["host_available_bytes"] is None:
        raise SystemExit("Readable WSL MemAvailable is required.")
    if environment_before["wsl_total_bytes"] is None:
        raise SystemExit("Readable WSL MemTotal is required.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (
        args.run_dir
        or args.artifact_root
        / f"p{args.degree}_h{args.h_nm:g}_{args.run_kind}_mpi{args.mpi_size}_{timestamp}"
    ).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    args.run_dir = run_dir
    progress_path = run_dir / "progress_3d.jsonl"
    timeline_path = run_dir / "memory_timeline.csv"
    stdout_path = run_dir / "worker_stdout.txt"
    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task033_full3d_watchdog",
        "--worker",
        "--degree",
        str(args.degree),
        "--h-nm",
        str(args.h_nm),
        "--run-kind",
        args.run_kind,
        "--profile",
        args.profile,
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
    terminated_for_authority_unreadable = False
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
        )
        previous: dict[str, Any] | None = None
        while True:
            elapsed = time.perf_counter() - started
            row = _sample(process.pid, progress_path, elapsed)
            _add_cpu_core_equivalents(row, previous)
            previous = row
            rows.append(row)
            process_tree_mb = row.get("mpi_process_tree_rss_mb")
            process_tree_swap_mb = row.get("mpi_process_tree_swap_mb")
            cgroup_mb = (
                row.get("container_cgroup_current_mb")
                if row.get("job_cgroup_dedicated") is True
                else 0.0
            )
            cgroup_swap_mb = (
                row.get("container_swap_current_mb")
                if row.get("job_cgroup_dedicated") is True
                else 0.0
            )
            authority_readable = all(
                isinstance(value, (int, float))
                for value in (
                    process_tree_mb, process_tree_swap_mb, cgroup_mb, cgroup_swap_mb
                )
            )
            authority_gib = (
                None
                if not authority_readable
                else max(float(process_tree_mb), float(cgroup_mb)) / 1024.0
            )
            if authority_gib is not None:
                warning_triggered |= authority_gib >= args.warning_gib
            if process.poll() is None and not authority_readable:
                terminated_for_authority_unreadable = True
                _terminate(process)
            elif (
                process.poll() is None
                and authority_gib is not None
                and authority_gib >= args.terminate_gib
            ):
                terminated_for_memory = True
                _terminate(process)
            elif process.poll() is None and elapsed >= args.timeout_seconds:
                terminated_for_timeout = True
                _terminate(process)
            if process.poll() is not None:
                break
            time.sleep(args.poll_interval)
        return_code = int(process.returncode or 0)

    with timeline_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    solver_path = run_dir / "run_summary.json"
    solver_summary = (
        json.loads(solver_path.read_text(encoding="utf-8"))
        if solver_path.is_file()
        else {}
    )
    events = _read_progress_events(progress_path)
    sampler = _sampler_summary(rows)
    sampler["poll_interval_seconds"] = args.poll_interval
    no_swap = bool(
        sampler["max_process_tree_swap_mb"] == 0.0
        and (
            not sampler["dedicated_job_cgroup_observed"]
            or sampler["max_container_swap_current_mb"] == 0.0
        )
    )
    qualification = _qualify(
        args=args,
        solver_summary=solver_summary,
        events=events,
        return_code=return_code,
        terminated_for_memory=terminated_for_memory,
        terminated_for_timeout=terminated_for_timeout,
        terminated_for_authority_unreadable=terminated_for_authority_unreadable,
        no_swap=no_swap,
        observed_worker_rank_count=sampler["max_observed_worker_rank_count"],
    )
    source_head_after = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    source_status_after = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).strip()
    source_stable = bool(
        source_head_after == source_before["commit_sha"] and not source_status_after
    )
    qualification["checks"]["source_stable_and_clean_after"] = source_stable
    if not source_stable:
        qualification["failures"].append("source_stable_and_clean_after")
        qualification["pass"] = False
    status = (
        "assembly_calibration_pass"
        if qualification["pass"] and args.run_kind == "assembly-only"
        else "factorization_calibration_pass"
        if qualification["pass"] and args.run_kind == "factorization-only"
        else "full3d_reference_pass"
        if qualification["pass"]
        else "formal_not_pass"
    )
    matrix = solver_summary.get("matrix_stats") or {}
    record = {
        "schema_version": "task033.full3d-watchdog.v1",
        "benchmark_id": "task033_target_full3d_watchdog",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "degree": args.degree,
        "h_nm": args.h_nm,
        "run_kind": args.run_kind,
        "mpi_size": args.mpi_size,
        "profile": args.profile,
        "command": command,
        "source": {
            **source_before,
            "branch": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=ROOT, text=True
            ).strip(),
            "head_after_sha": source_head_after,
            "status_after": source_status_after,
            "stable_and_clean_after": source_stable,
        },
        "p4_prerequisite_gate": p4_gate,
        "resource_policy": {
            "swap_allowed": args.allow_swap,
            "warning_gib": args.warning_gib,
            "termination_gib": args.terminate_gib,
            "termination_authority": (
                "max(process-tree RSS, dedicated job cgroup memory.current when present)"
            ),
            "timeout_seconds": args.timeout_seconds,
            "formal_no_swap_authority": "process-tree VmSwap plus dedicated job cgroup swap",
            "wsl_global_pswp_role": "diagnostic_only",
            "mumps_ooc_role": "explicit_scratch_profile_not_linux_swap",
            "effective_limit": effective,
        },
        "environment_before": environment_before,
        "environment_after": _resource_snapshot(),
        "warning_triggered": warning_triggered,
        "terminated_for_memory": terminated_for_memory,
        "terminated_for_timeout": terminated_for_timeout,
        "terminated_for_authority_unreadable": (
            terminated_for_authority_unreadable
        ),
        "no_swap": no_swap,
        "resource_authority": sampler,
        "calibration": {
            "exact_rows": matrix.get("matrix_rows"),
            "exact_assembled_nnz": matrix.get("matrix_nnz_used"),
            "matrix_petsc_memory_bytes": matrix.get("matrix_memory_bytes"),
            "matrix_payload_estimate_bytes": matrix.get(
                "matrix_memory_estimate_bytes"
            ),
            "num_nedelec_dofs": solver_summary.get("num_nedelec_dofs"),
            "num_auxiliary_dofs": solver_summary.get(
                "stage4_dtn_num_auxiliary_dofs"
            ),
            "floquet_constraint_rows": solver_summary.get(
                "floquet_num_constraints"
            ),
            "floquet_constraint_raw_map_nnz": solver_summary.get(
                "floquet_raw_map_nnz"
            ),
            "floquet_constraint_timings_seconds": solver_summary.get(
                "floquet_constraint_timings_seconds"
            ),
            "floquet_created_dense_boundary_square": solver_summary.get(
                "floquet_created_dense_boundary_square"
            ),
            "dtn_auxiliary_block_stats": solver_summary.get(
                "stage4_dtn_auxiliary_block_stats"
            ),
            "explicit_chac_constructed": solver_summary.get(
                "explicit_chac_constructed"
            ),
            "factorization_or_solve_stage_seen": _factorization_stage_seen(events),
        },
        "matrix_inventory": {
            "base": solver_summary.get("stage4_dtn_base_matrix_stats"),
            "augmented": solver_summary.get(
                "stage4_dtn_augmented_matrix_stats_after_finalize"
            ),
            "final": matrix,
            "constraint_transform": solver_summary.get(
                "constraint_matrix_transform"
            ),
        },
        "timings_seconds": solver_summary.get("timings_seconds"),
        "historical_peak_upper_bound_mb": _historical_peak_upper_bound(
            events, solver_summary
        ),
        "qualification": qualification,
        "return_code": return_code,
        "solver_summary_sha256": _sha256(solver_path),
        "timeline_sha256": _sha256(timeline_path),
        "progress_sha256": _sha256(progress_path),
        "raw_evidence": {
            "run_directory": _path_from_root(run_dir),
            "solver_summary": _path_from_root(solver_path),
            "timeline": _path_from_root(timeline_path),
            "progress": _path_from_root(progress_path),
            "stdout": _path_from_root(stdout_path),
        },
        "solver_summary": solver_summary,
    }
    record_path = args.record or (run_dir / "watchdog_summary.json")
    if not record_path.is_absolute():
        record_path = ROOT / record_path
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": status,
                "degree": args.degree,
                "h_nm": args.h_nm,
                "run_kind": args.run_kind,
                "memory_authority_gib": sampler["memory_authority_gib"],
                "combined_memory_swap_authority_gib": sampler[
                    "combined_memory_swap_authority_gib"
                ],
                "no_swap": no_swap,
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
