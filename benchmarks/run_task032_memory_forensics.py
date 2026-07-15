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
)
from benchmarks.run_task031_memory_forensics import _sampler_summary


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "benchmarks" / "artifacts" / "cases" / "080" / "phase10"


def _worker_command(
    args: argparse.Namespace,
    record_path: Path,
    stage_path: Path,
) -> list[str]:
    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task032_phase6_augmented",
        "--h-nm",
        str(args.h_nm),
        "--requested-modes",
        str(args.requested_modes),
        "--candidate-modes",
        str(args.candidate_modes),
        "--solver-path",
        args.solver_path,
        "--output",
        str(record_path),
        "--memory-stages",
        str(stage_path),
        "--container-image",
        args.container_image,
        "--container-digest",
        args.container_digest,
        "--host-environment-id",
        args.host_environment_id,
    ]
    if args.verified_clean_sha:
        command.extend(("--verified-clean-sha", args.verified_clean_sha))
    elif args.allow_dirty_research:
        command.append("--allow-dirty-research")
    return command


def run(args: argparse.Namespace) -> int:
    if args.mpi_size < 1:
        raise SystemExit("--mpi-size must be positive.")
    if args.h_nm <= 2.0 and not args.unlock_h2:
        raise SystemExit(
            "Task32 h2 is locked until h5/h3 numerics, two independent memory "
            "predictions, <=5 GiB upper bounds, clean source, zero swap, and watchdog gates pass."
        )
    if args.solver_path == "augmented" and "minimal" in args.case_label:
        raise SystemExit("The case label and solver lifecycle disagree.")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.run_dir or (
        args.artifact_root
        / f"{args.case_label}_h{args.h_nm:g}_m{args.requested_modes}_mpi{args.mpi_size}_{timestamp}"
    )
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    record_path = run_dir / "solver_record.json"
    stage_path = run_dir / "memory_stages.jsonl"
    timeline_path = run_dir / "memory_timeline.csv"
    stdout_path = run_dir / "worker_stdout.txt"
    command = _worker_command(args, record_path, stage_path)
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "BENCHMARK_EXACT_COMMAND": " ".join(command),
        }
    )

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
    numeric_pass = bool(
        return_code == 0
        and solver_record.get("qualification", {}).get("integration_pass")
        and float(
            solver_record.get("solve", {}).get(
                "true_relative_residual", float("inf")
            )
        )
        <= 1.0e-9
    )
    no_swap = bool(
        memory.get("wsl_pswpin_delta_pages") == 0
        and memory.get("wsl_pswpout_delta_pages") == 0
    )
    summary = {
        "schema_version": 1,
        "benchmark_id": "task032_external_simultaneous_memory_forensics",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "case_label": args.case_label,
        "solver_path": args.solver_path,
        "h_nm": args.h_nm,
        "requested_modes_per_direction": args.requested_modes,
        "mpi_size": args.mpi_size,
        "command": command,
        "return_code": return_code,
        "numeric_pass": numeric_pass,
        "no_swap": no_swap,
        "warning_threshold_gib": args.warning_gib,
        "termination_threshold_gib": args.terminate_gib,
        "warning_triggered": warning_triggered,
        "terminated_for_memory": terminated_for_memory,
        "memory": memory,
        "object_payload_ledger": solver_record.get("object_payload_ledger"),
        "solver_record": str(record_path.relative_to(ROOT)),
        "timeline": str(timeline_path.relative_to(ROOT)),
        "stage_markers": str(stage_path.relative_to(ROOT)),
        "semantics": (
            "External 0.25 s samples sum current RSS of live MPI workers at one instant. "
            "Container cgroup and swap are separate authorities; historical rank peaks are not summed."
        ),
    }
    summary_path = run_dir / "memory_sampler_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.summary_output is not None:
        promoted = (
            args.summary_output
            if args.summary_output.is_absolute()
            else ROOT / args.summary_output
        )
        promoted.parent.mkdir(parents=True, exist_ok=True)
        promoted.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if numeric_pass and no_swap and not terminated_for_memory else (return_code or 2)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task32 external simultaneous RSS/cgroup/swap/stage sampler."
    )
    parser.add_argument("--h-nm", type=float, default=5.0)
    parser.add_argument("--requested-modes", type=int, default=120)
    parser.add_argument("--candidate-modes", type=int, default=240)
    parser.add_argument("--mpi-size", type=int, default=4)
    parser.add_argument(
        "--solver-path",
        choices=("augmented", "modal-schur-fast", "modal-schur-memory-minimal"),
        required=True,
    )
    parser.add_argument("--case-label", required=True)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--warning-gib", type=float, default=4.5)
    parser.add_argument("--terminate-gib", type=float, default=6.0)
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--allow-dirty-research", action="store_true")
    parser.add_argument("--unlock-h2", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="Optional lightweight tracked copy of the sampler summary.",
    )
    parser.add_argument("--container-image", default="myfenics-stage4:task28")
    parser.add_argument(
        "--container-digest",
        default="sha256:08c61bc59cdd4f3dfc88d70ca14eea3da48fba3a27d2c4ec052d3b5a6f38476d",
    )
    parser.add_argument("--host-environment-id", default="windows-docker-desktop")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
