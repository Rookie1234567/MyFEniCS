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


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "benchmarks" / "artifacts" / "cases" / "070"


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_provenance(
    verified_clean_sha: str | None, *, allow_dirty_research: bool
) -> dict[str, Any]:
    head = _git("rev-parse", "HEAD")
    tracked_status = _git("status", "--porcelain", "--untracked-files=no")
    if head is None or tracked_status is None:
        raise SystemExit("Cannot verify Task31 source identity and cleanliness.")
    if verified_clean_sha is not None:
        verified = verified_clean_sha.strip().lower()
        if len(verified) != 40 or any(char not in "0123456789abcdef" for char in verified):
            raise SystemExit("--verified-clean-sha must be a full hexadecimal Git SHA.")
        if head.lower() != verified:
            raise SystemExit(
                f"Clean-source attestation {verified} does not match mounted HEAD {head}."
            )
        return {
            "commit_sha": head,
            "tracked_source_dirty": False,
            "verification": "host_git_clean_attestation",
            "verified_clean_sha": verified,
        }
    dirty = bool(tracked_status)
    if dirty and not allow_dirty_research:
        raise SystemExit(
            "Tracked source is dirty. Commit Task31 code before a qualified memory run, "
            "or pass --allow-dirty-research for explicitly non-qualifying exploration."
        )
    return {
        "commit_sha": head,
        "tracked_source_dirty": dirty,
        "verification": "local_git_status",
        "verified_clean_sha": None,
    }


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
            "current/peak is reported separately. Per-rank historical peaks are not summed."
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
            "BENCHMARK_COMMIT_SHA": provenance["commit_sha"],
            "BENCHMARK_BRANCH": _git("branch", "--show-current") or "unknown",
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
        )
        previous: dict[str, Any] | None = None
        while True:
            row = _sample(process.pid, stage_path, time.perf_counter() - started)
            _add_cpu_core_equivalents(row, previous)
            previous = row
            rows.append(row)
            current_gib = float(row["container_cgroup_current_mb"] or 0.0) / 1024.0
            if current_gib >= args.warning_gib:
                warning_triggered = True
            if current_gib >= args.terminate_gib and process.poll() is None:
                terminated_for_memory = True
                process.terminate()
            if process.poll() is not None:
                break
            time.sleep(max(args.poll_interval, 0.05))
        return_code = int(process.returncode or 0)

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
    history = solver_record.get("history") or []
    screen_pass = bool(
        args.screen_only
        and return_code == 0
        and solver_record
        and history
        and float(history[-1].get("true_relative_residual", float("inf")))
        < float(history[0].get("true_relative_residual", float("inf")))
    )
    numeric_pass = bool(
        screen_pass
        or (
            return_code == 0
            and int(solver_record.get("ksp_reason", 0)) > 0
            and float(solver_record.get("full_augmented_true_residual", float("inf")))
            <= args.rta_threshold
            and solver_record.get("official_rta")
        )
    )
    summary = {
        "task": "Task031",
        "case": args.case_label,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": provenance,
        "command": command,
        "return_code": return_code,
        "numeric_pass": numeric_pass,
        "screen_only": args.screen_only,
        "screen_pass": screen_pass,
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
    return 0 if numeric_pass else (return_code or 2)


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
