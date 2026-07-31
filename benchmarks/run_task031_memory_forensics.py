from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _sample,
    _stage_peaks,
)
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "benchmarks" / "artifacts" / "cases" / "070"


def _memory_authority_gib(row: dict[str, Any]) -> float:
    process_tree_mb = float(row.get("mpi_process_tree_rss_mb") or 0.0)
    dedicated_cgroup_mb = (
        float(row.get("container_cgroup_current_mb") or 0.0)
        if row.get("job_cgroup_dedicated") is True
        else 0.0
    )
    return max(process_tree_mb, dedicated_cgroup_mb) / 1024.0


def _task031_solver_disposition(
    *,
    screen_only: bool,
    return_code: int,
    terminated_for_memory: bool,
    solver_record: dict[str, Any],
) -> dict[str, Any]:
    history = solver_record.get("history") or []
    screen_trend_positive = bool(
        screen_only
        and len(history) >= 2
        and float(history[-1].get("true_relative_residual", float("inf")))
        < float(history[0].get("true_relative_residual", float("inf")))
    )
    worker_formal_pass = bool(
        not screen_only
        and return_code == 0
        and solver_record.get("status") == "formal_pass"
        and solver_record.get("formal_pass") is True
    )
    worker_numeric_pass = bool(
        solver_record.get("numeric_solver_pass", worker_formal_pass)
    )
    worker_physics_pass = bool(
        solver_record.get("physics_pass", worker_formal_pass)
    )
    if terminated_for_memory:
        status = "resource_controlled_stop"
    elif screen_only:
        status = (
            "screen_trend_positive"
            if screen_trend_positive
            else "screen_no_positive_trend"
        )
    elif worker_formal_pass:
        status = "formal_pass"
    elif solver_record.get("status") == "formal_pass":
        status = "worker_formal_not_pass"
    elif solver_record.get("status") in {
        "numeric_not_pass",
        "physics_not_pass",
        "source_identity_not_pass",
        "controlled_negative_source_identity",
        "experimental_unqualified",
    }:
        status = str(solver_record["status"])
    elif return_code != 0:
        status = "worker_process_failed"
    else:
        status = str(solver_record.get("status") or "worker_record_missing")
    preserve_worker_numeric = bool(
        not screen_only
        and not terminated_for_memory
        and solver_record.get("status")
        in {
            "formal_pass",
            "numeric_not_pass",
            "physics_not_pass",
            "source_identity_not_pass",
            "controlled_negative_source_identity",
            "experimental_unqualified",
        }
    )
    return {
        "status": status,
        "worker_status": solver_record.get("status"),
        "screen_trend_positive": screen_trend_positive,
        "numeric_pass": worker_numeric_pass if preserve_worker_numeric else False,
        "physics_pass": worker_physics_pass if preserve_worker_numeric else False,
        "formal_pass": worker_formal_pass and status == "formal_pass",
    }


def _apply_task031_source_identity(
    disposition: dict[str, Any], *, source_identity_stable: bool
) -> dict[str, Any]:
    result = dict(disposition)
    if result.get("formal_pass") and not source_identity_stable:
        result["status"] = "controlled_negative_source_identity"
        result["formal_pass"] = False
    return result


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_state() -> dict[str, Any]:
    head = _git("rev-parse", "HEAD")
    source_status = _git("status", "--porcelain", "--untracked-files=all")
    return {
        "commit_sha": head,
        "capture_ok": head is not None and source_status is not None,
        "tracked_source_dirty": (
            None if source_status is None else bool(source_status)
        ),
    }


def _source_provenance(
    verified_clean_sha: str | None, *, allow_dirty_research: bool
) -> dict[str, Any]:
    state = _source_state()
    if state["capture_ok"] is not True:
        raise SystemExit("Cannot verify Task31 source identity and cleanliness.")
    head = str(state["commit_sha"])
    dirty = bool(state["tracked_source_dirty"])
    if verified_clean_sha is not None:
        verified = verified_clean_sha.strip().lower()
        if len(verified) != 40 or any(
            char not in "0123456789abcdef" for char in verified
        ):
            raise SystemExit("--verified-clean-sha must be a full hexadecimal Git SHA.")
        if head.lower() != verified:
            raise SystemExit(
                f"Clean-source attestation {verified} does not match mounted HEAD {head}."
            )
    if dirty and not allow_dirty_research:
        raise SystemExit(
            "Tracked source is dirty. Commit Task31 code before a qualified memory run, "
            "or pass --allow-dirty-research for explicitly non-qualifying exploration."
        )
    return {
        "commit_sha": head,
        "capture_ok": True,
        "tracked_source_dirty": dirty,
        "verification": (
            "local_git_status_plus_host_attestation"
            if verified_clean_sha is not None
            else "local_git_status"
        ),
        "verified_clean_sha": (
            verified_clean_sha.strip().lower()
            if verified_clean_sha is not None
            else None
        ),
    }


def _task031_source_identity_stable(
    source_at_start: dict[str, Any], source_at_end: dict[str, Any]
) -> bool:
    return bool(
        source_at_start.get("capture_ok") is True
        and source_at_end.get("capture_ok") is True
        and source_at_start.get("commit_sha") == source_at_end.get("commit_sha")
        and source_at_start.get("tracked_source_dirty") is False
        and source_at_end.get("tracked_source_dirty") is False
    )


def _worker_command(args: argparse.Namespace, record_path: Path, heavy_dir: Path) -> list[str]:
    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_workstation_iterative",
        "--h-nm",
        str(args.h_nm),
        "--num-slabs",
        str(args.num_slabs),
        "--overlap-layers",
        str(args.overlap_layers),
        "--ilu-levels",
        str(args.ilu_levels),
        "--ksp-type",
        args.ksp_type,
        "--smoother-ksp-type",
        args.smoother_ksp_type,
        "--restart",
        str(args.restart),
        "--selective-diagonal-boundary-slabs",
        str(args.selective_diagonal_boundary_slabs),
        "--max-it",
        str(args.max_it),
        "--rtol",
        str(args.rtol),
        "--rta-threshold",
        str(args.rta_threshold),
        "--monitor-stride",
        str(args.monitor_stride),
        "--case-label",
        args.case_label,
        "--record",
        str(record_path),
        "--results-dir",
        str(heavy_dir),
    ]
    for enabled, flag in (
        (args.post_smooth, "--post-smooth"),
        (args.subdomain_local_shift, "--subdomain-local-shift"),
        (args.factor_only_storage, "--factor-only-storage"),
        (args.certify_pc, "--certify-pc"),
        (args.compact_lifecycle, "--compact-lifecycle"),
        (args.matrix_free_fine, "--matrix-free-fine"),
    ):
        if enabled:
            command.append(flag)
    return command


def _sampler_summary(rows: list[dict[str, Any]], *, poll_interval: float) -> dict[str, Any]:
    pswpin = [
        int(row["wsl_pswpin_pages"])
        for row in rows
        if row.get("wsl_pswpin_pages") is not None
    ]
    pswpout = [
        int(row["wsl_pswpout_pages"])
        for row in rows
        if row.get("wsl_pswpout_pages") is not None
    ]
    rss_peak = max(rows, key=lambda row: float(row["worker_rank_rss_sum_mb"]), default=None)
    cgroup_peak = max(
        rows,
        key=lambda row: float(row["container_cgroup_current_mb"] or 0.0),
        default=None,
    )
    return {
        "poll_interval_seconds": poll_interval,
        "sample_count": len(rows),
        "max_simultaneous_worker_rss_mb": (
            float(rss_peak["worker_rank_rss_sum_mb"]) if rss_peak else 0.0
        ),
        "max_simultaneous_worker_rss_gib": (
            float(rss_peak["worker_rank_rss_sum_mb"]) / 1024.0 if rss_peak else 0.0
        ),
        "max_simultaneous_worker_rss_stage": rss_peak["stage"] if rss_peak else None,
        "max_container_cgroup_current_mb": (
            float(cgroup_peak["container_cgroup_current_mb"] or 0.0)
            if cgroup_peak
            else 0.0
        ),
        "max_container_cgroup_current_gib": (
            float(cgroup_peak["container_cgroup_current_mb"] or 0.0) / 1024.0
            if cgroup_peak
            else 0.0
        ),
        "max_container_cgroup_current_stage": cgroup_peak["stage"] if cgroup_peak else None,
        "container_cgroup_peak_mb_at_end": (
            rows[-1].get("container_cgroup_peak_mb") if rows else None
        ),
        "wsl_pswpin_delta_pages": max(pswpin) - min(pswpin) if pswpin else None,
        "wsl_pswpout_delta_pages": max(pswpout) - min(pswpout) if pswpout else None,
        "stage_peaks": _stage_peaks(rows),
        "semantics": (
            "Worker RSS is the simultaneous sum sampled from live MPI ranks; cgroup "
            "current/peak is reported separately and is formal only for a dedicated job "
            "cgroup. Per-rank historical peaks are not summed."
        ),
        "memory_authority_semantics": (
            "max(process-tree RSS, dedicated job cgroup memory.current when present); "
            "WSL /init.scope is diagnostic only"
        ),
    }


def run(args: argparse.Namespace) -> int:
    if args.mpi_size < 1:
        raise SystemExit("--mpi-size must be positive.")
    if args.h_nm <= 2.0 and not args.unlock_h2:
        raise SystemExit("h2 is locked; pass --unlock-h2 only after the documented h3 gates.")
    provenance = _source_provenance(
        args.verified_clean_sha, allow_dirty_research=args.allow_dirty_research
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.run_dir or (
        args.artifact_root
        / f"{args.case_label}_mpi{args.mpi_size}_{args.ksp_type}{args.restart}_{timestamp}"
    )
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    record_path = run_dir / "solver_record.json"
    heavy_dir = run_dir / "heavy"
    timeline_path = run_dir / "memory_timeline.csv"
    stdout_path = run_dir / "worker_stdout.txt"
    stage_path = record_path.with_name(record_path.stem + "_memory_stages.jsonl")
    command = _worker_command(args, record_path, heavy_dir)
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "BENCHMARK_EXACT_COMMAND": " ".join(command),
            "BENCHMARK_COMMIT_SHA": provenance["commit_sha"] or "unknown",
            "BENCHMARK_CONTAINER_IMAGE": os.environ.get(
                "BENCHMARK_CONTAINER_IMAGE", "unknown"
            ),
            "BENCHMARK_CONTAINER_DIGEST": os.environ.get(
                "BENCHMARK_CONTAINER_DIGEST", "unknown"
            ),
        }
    )
    if provenance["verified_clean_sha"] is not None:
        environment["BENCHMARK_VERIFIED_CLEAN_SHA"] = provenance["verified_clean_sha"]
    elif provenance["tracked_source_dirty"]:
        environment["BENCHMARK_GIT_DIRTY"] = "true"

    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    warning_triggered = False
    terminated_for_memory = False
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            **worker_process_group_popen_kwargs(),
        )
        try:
            previous: dict[str, Any] | None = None
            while True:
                row = _sample(process.pid, stage_path, time.perf_counter() - started)
                _add_cpu_core_equivalents(row, previous)
                previous = row
                rows.append(row)
                authority_gib = _memory_authority_gib(row)
                if authority_gib >= args.warning_gib:
                    warning_triggered = True
                if authority_gib >= args.terminate_gib and process.poll() is None:
                    terminated_for_memory = True
                    terminate_process_tree(process)
                if process.poll() is not None:
                    break
                time.sleep(max(args.poll_interval, 0.05))
            return_code = int(process.returncode or 0)
        except BaseException as primary_error:
            if process.poll() is None:
                try:
                    terminate_process_tree(process)
                except Exception as cleanup_error:
                    primary_error.add_note(
                        "worker process-group cleanup also failed: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    )
            raise

    with timeline_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    solver_record = (
        json.loads(record_path.read_text(encoding="utf-8"))
        if record_path.is_file()
        else {}
    )
    memory = _sampler_summary(rows, poll_interval=args.poll_interval)
    source_at_end = _source_state()
    source_identity_stable = _task031_source_identity_stable(
        provenance, source_at_end
    )
    disposition = _task031_solver_disposition(
        screen_only=args.screen_only,
        return_code=return_code,
        terminated_for_memory=terminated_for_memory,
        solver_record=solver_record,
    )
    disposition = _apply_task031_source_identity(
        disposition,
        source_identity_stable=source_identity_stable,
    )
    summary = {
        "task": "Task031",
        "case": args.case_label,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": provenance,
        "source_at_end": source_at_end,
        "source_identity_stable": source_identity_stable,
        "command": command,
        "return_code": return_code,
        "status": disposition["status"],
        "numeric_pass": disposition["numeric_pass"],
        "physics_pass": disposition["physics_pass"],
        "formal_pass": disposition["formal_pass"],
        "screen_only": args.screen_only,
        "screen_trend_positive": disposition["screen_trend_positive"],
        "warning_threshold_gib": args.warning_gib,
        "terminate_threshold_gib": args.terminate_gib,
        "warning_triggered": warning_triggered,
        "terminated_for_memory": terminated_for_memory,
        "memory": memory,
        "solver_record": str(record_path),
        "timeline": str(timeline_path),
    }
    (run_dir / "memory_sampler_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if disposition["formal_pass"] else (return_code or 2)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task31 external simultaneous RSS/cgroup sampler for iterative candidates."
    )
    parser.add_argument("--h-nm", type=float, default=5.0)
    parser.add_argument("--mpi-size", type=int, default=4)
    parser.add_argument("--num-slabs", type=int, default=16)
    parser.add_argument("--overlap-layers", type=float, default=0.25)
    parser.add_argument("--ilu-levels", type=int, default=0)
    parser.add_argument("--ksp-type", choices=("fgmres", "gmres", "tfqmr", "bcgs"), default="gmres")
    parser.add_argument(
        "--smoother-ksp-type",
        choices=("gmres", "richardson"),
        default="gmres",
    )
    parser.add_argument("--restart", type=int, default=70)
    parser.add_argument("--selective-diagonal-boundary-slabs", type=int, default=0)
    parser.add_argument("--max-it", type=int, default=5000)
    parser.add_argument("--rtol", type=float, default=1.0e-6)
    parser.add_argument("--rta-threshold", type=float, default=1.1e-6)
    parser.add_argument("--monitor-stride", type=int, default=70)
    parser.add_argument("--case-label", default="task031_candidate")
    parser.add_argument("--post-smooth", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--subdomain-local-shift", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument(
        "--factor-only-storage", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument(
        "--certify-pc",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Explicitly require fixed-PC certification for FGMRES research runs. "
            "The worker always certifies every non-FGMRES outer KSP and fails closed."
        ),
    )
    parser.add_argument(
        "--compact-lifecycle", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument(
        "--matrix-free-fine", action=argparse.BooleanOptionalAction, default=False
    )
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--warning-gib", type=float, default=9.5)
    parser.add_argument("--terminate-gib", type=float, default=11.0)
    parser.add_argument("--unlock-h2", action="store_true")
    parser.add_argument("--screen-only", action="store_true")
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--allow-dirty-research", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
