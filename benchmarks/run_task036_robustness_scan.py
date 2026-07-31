from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POINTS = ROOT / "benchmarks" / "task036_robustness_scan_points.csv"
MPI_SIZE = 8


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
    ).strip()


def _load_points(
    path: Path,
    *,
    rounds: set[str],
    point_ids: set[str],
    limit: int | None,
) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    selected = [
        row
        for row in rows
        if (not rounds or row["round"] in rounds)
        and (not point_ids or row["point_id"] in point_ids)
    ]
    return selected if limit is None else selected[:limit]


def _point_values(row: dict[str, str]) -> dict[str, Any]:
    return {
        "point_id": row["point_id"],
        "degree": int(row["nedelec_degree"]),
        "h_nm": float(row["h_nm"]),
        "height_nm": float(row["height_nm"]),
        "width_x_nm": float(row["width_x_nm"]),
        "grazing_deg": float(row["grazing_deg"]),
        "azimuth_deg": float(row["azimuth_deg"]),
        "polarization": row["incident_polarization"].lower(),
        "axis_counts": (
            int(row["nx"]),
            int(row["ny"]),
            int(row["nz"]),
        ),
        "initial_m": int(row["initial_m_per_direction"]),
    }


def _exclusive_cpu_sets(
    max_parallel: int,
    *,
    mpi_size: int = MPI_SIZE,
) -> tuple[tuple[int, ...], ...]:
    if not hasattr(os, "sched_getaffinity"):
        raise RuntimeError(
            "Task036 parallel dispatch requires Linux CPU-affinity support."
        )
    available = tuple(sorted(os.sched_getaffinity(0)))
    required = max_parallel * mpi_size
    if len(available) < required:
        raise RuntimeError(
            "Task036 parallel dispatch needs "
            f"{required} CPUs for {max_parallel} MPI{mpi_size} jobs, "
            f"but only {len(available)} are available."
        )
    return tuple(
        available[index * mpi_size : (index + 1) * mpi_size]
        for index in range(max_parallel)
    )


def _mpi_binding_environment(cpu_set: tuple[int, ...]) -> dict[str, str]:
    cpu_list = ",".join(str(cpu) for cpu in cpu_set)
    return {
        "OMPI_MCA_hwloc_base_cpu_list": cpu_list,
        "OMPI_MCA_hwloc_base_binding_policy": "cpu-list:ordered",
        "OMPI_MCA_hwloc_base_report_bindings": "true",
    }


def _full3d_command(
    point: dict[str, Any],
    *,
    source_sha: str,
    run_dir: Path,
    timeout_seconds: float,
) -> list[str]:
    nx, ny, nz = point["axis_counts"]
    return [
        sys.executable,
        "-m",
        "benchmarks.run_task033_full3d_watchdog",
        "--degree",
        str(point["degree"]),
        "--h-nm",
        str(point["h_nm"]),
        "--polarization-kind",
        point["polarization"],
        "--incident-grazing-deg",
        str(point["grazing_deg"]),
        "--incident-phi-deg",
        str(point["azimuth_deg"]),
        "--grating-height-nm",
        str(point["height_nm"]),
        "--grating-width-x-nm",
        str(point["width_x_nm"]),
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "8",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--task036-forward-robustness-gate",
        "--task036-mesh-axis-cell-counts",
        str(nx),
        str(ny),
        str(nz),
        "--task036-y-invariant-n0-alias-preflight",
        "--task036-dtn-direct-projection-audit",
        "--verified-clean-sha",
        source_sha,
        "--timeout-seconds",
        str(timeout_seconds),
        "--run-dir",
        str(run_dir),
    ]


def _hybrid_command(
    point: dict[str, Any],
    *,
    source_sha: str,
    full3d_reference: Path,
    run_dir: Path,
    mode_count: int,
    timeout_seconds: float,
    warning_gib: float | None,
    terminate_gib: float | None,
) -> list[str]:
    nx, ny, nz = point["axis_counts"]
    command = [
        sys.executable,
        "-m",
        "benchmarks.run_task033_memory_watchdog",
        "--target",
        "hybrid",
        "--case-label",
        f"task036_{point['point_id']}_m{mode_count}",
        "--degree",
        str(point["degree"]),
        "--h-nm",
        str(point["h_nm"]),
        "--modal-degree",
        str(point["degree"]),
        "--modal-h-nm",
        str(point["h_nm"]),
        "--mpi-size",
        "8",
        "--requested-modes",
        str(mode_count),
        "--candidate-modes",
        str(2 * mode_count),
        "--solver-path",
        "modal-schur-memory-minimal",
        "--internal-propagation-model",
        "full3d_uniform_cg",
        "--internal-traction-model",
        "scalar_cg_discrete_derivative",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--full3d-reference",
        str(full3d_reference),
        "--full3d-reference-sha256",
        _sha256(full3d_reference),
        "--incident-grazing-deg",
        str(point["grazing_deg"]),
        "--incident-phi-deg",
        str(point["azimuth_deg"]),
        "--grating-height-nm",
        str(point["height_nm"]),
        "--grating-width-x-nm",
        str(point["width_x_nm"]),
        "--polarization-kind",
        point["polarization"],
        "--task036-domain-robustness-gate",
        "--task036-mesh-axis-cell-counts",
        str(nx),
        str(ny),
        str(nz),
        "--task036-y-invariant-n0-alias-preflight",
        "--task036-dtn-direct-projection-audit",
        "--task036-scalar-stage4-reciprocal-basis",
        "--verified-clean-sha",
        source_sha,
        "--host-environment-id",
        "WSL2-Ubuntu-24.04",
        "--timeout-seconds",
        str(timeout_seconds),
        "--run-dir",
        str(run_dir),
    ]
    if warning_gib is not None:
        command.extend(("--warning-gib", str(warning_gib)))
    if terminate_gib is not None:
        command.extend(("--terminate-gib", str(terminate_gib)))
    return command


def _run_command(
    *,
    point_id: str,
    stage: str,
    command: list[str],
    run_dir: Path,
    cpu_set: tuple[int, ...],
) -> dict[str, Any]:
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    if run_dir.exists():
        return {
            "point_id": point_id,
            "stage": stage,
            "status": "failed",
            "failure_kind": "existing_artifact_requires_validation",
            "failure_detail": (
                "Task036 does not reuse an existing run directory without an "
                "independent schema/source/input/status/hash validator."
            ),
            "return_code": None,
            "run_dir": str(run_dir),
            "exclusive_cpu_set": list(cpu_set),
        }
    temporary = run_dir.parent / f".{run_dir.name}_tmp"
    temporary.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.update(
        {
            "TMPDIR": str(temporary),
            "TMP": str(temporary),
            "TEMP": str(temporary),
            "XDG_CACHE_HOME": str(temporary / "xdg"),
            "MUMPS_OOC_TMPDIR": str(temporary / "mumps"),
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            **_mpi_binding_environment(cpu_set),
        }
    )
    launcher_command = [
        "taskset",
        "--cpu-list",
        ",".join(str(cpu) for cpu in cpu_set),
        *command,
    ]
    log_path = run_dir.parent / f"{run_dir.name}.launcher.log"
    started = datetime.now(timezone.utc).isoformat()
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(
            launcher_command,
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return {
        "point_id": point_id,
        "stage": stage,
        "status": "completed" if process.returncode == 0 else "failed",
        "return_code": int(process.returncode),
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "launcher_log": str(log_path),
        "command": command,
        "launcher_command": launcher_command,
        "exclusive_cpu_set": list(cpu_set),
        "mpi_binding": {
            "mpi_size": MPI_SIZE,
            "binding_policy": "cpu-list:ordered",
            "mapping_policy": "explicit_ordered_cpu_lease",
            "report_bindings": True,
        },
    }


def _append_ledger(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _run_batch(jobs: list[dict[str, Any]], max_parallel: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    leases: Queue[tuple[int, ...]] = Queue()
    for cpu_set in _exclusive_cpu_sets(max_parallel):
        leases.put(cpu_set)

    def run_with_cpu_lease(job: dict[str, Any]) -> dict[str, Any]:
        cpu_set = leases.get()
        try:
            return _run_command(**job, cpu_set=cpu_set)
        finally:
            leases.put(cpu_set)

    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = {
            executor.submit(run_with_cpu_lease, job): job["point_id"]
            for job in jobs
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    return sorted(results, key=lambda result: result["point_id"])


def _validate_parallel_policy(max_parallel: int, *, dry_run: bool) -> None:
    if not 1 <= max_parallel <= 5:
        raise SystemExit("--max-parallel must lie in [1, 5].")
    if not dry_run and max_parallel != 1:
        raise SystemExit(
            "Task036 heavy dispatch requires --max-parallel=1 until an "
            "aggregate cgroup/job-group memory coordinator is qualified."
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task036 V2 frozen-point Full3D-before-Hybrid dispatcher."
    )
    parser.add_argument("--points", type=Path, default=DEFAULT_POINTS)
    parser.add_argument("--round", action="append", default=[])
    parser.add_argument("--point-id", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--stage", choices=("full3d", "hybrid", "both"), default="both"
    )
    parser.add_argument("--mode-count", type=int)
    parser.add_argument("--max-parallel", type=int, default=1)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=7200.0)
    parser.add_argument("--hybrid-warning-gib", type=float)
    parser.add_argument("--hybrid-terminate-gib", type=float)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _validate_parallel_policy(args.max_parallel, dry_run=args.dry_run)
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit must be positive.")
    if args.timeout_seconds <= 0.0:
        raise SystemExit("--timeout-seconds must be positive.")
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--short", "--untracked-files=all")
    if head != args.verified_clean_sha or status:
        raise SystemExit(
            "Task036 formal dispatch requires exact HEAD and a clean worktree."
        )
    points_path = args.points if args.points.is_absolute() else ROOT / args.points
    selected_rows = _load_points(
        points_path.resolve(),
        rounds=set(args.round),
        point_ids=set(args.point_id),
        limit=args.limit,
    )
    if not selected_rows:
        raise SystemExit("No frozen Task036 points matched the selection.")
    artifact_root = args.artifact_root.resolve()
    ledger = (
        args.ledger.resolve()
        if args.ledger is not None
        else artifact_root / "scan_results.jsonl"
    )
    points = [_point_values(row) for row in selected_rows]

    full3d_jobs = [
        {
            "point_id": point["point_id"],
            "stage": "full3d",
            "command": _full3d_command(
                point,
                source_sha=head,
                run_dir=artifact_root / point["point_id"] / "full3d",
                timeout_seconds=args.timeout_seconds,
            ),
            "run_dir": artifact_root / point["point_id"] / "full3d",
        }
        for point in points
    ]
    if args.dry_run:
        rendered = {"full3d_jobs": full3d_jobs}
        if args.stage == "hybrid":
            rendered["note"] = "Hybrid commands require completed Full3D hashes."
        print(json.dumps(rendered, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.stage in {"full3d", "both"}:
        full3d_results = _run_batch(full3d_jobs, args.max_parallel)
        _append_ledger(ledger, full3d_results)
        if any(
            result["status"] == "failed" for result in full3d_results
        ):
            return 2

    if args.stage in {"hybrid", "both"}:
        hybrid_jobs: list[dict[str, Any]] = []
        for point in points:
            reference = (
                artifact_root
                / point["point_id"]
                / "full3d"
                / "watchdog_summary.json"
            )
            if not reference.is_file():
                raise SystemExit(
                    f"Missing same-input Full3D authority: {reference}"
                )
            mode_count = args.mode_count or point["initial_m"]
            run_dir = (
                artifact_root
                / point["point_id"]
                / f"hybrid_m{mode_count}"
            )
            hybrid_jobs.append(
                {
                    "point_id": point["point_id"],
                    "stage": f"hybrid_m{mode_count}",
                    "command": _hybrid_command(
                        point,
                        source_sha=head,
                        full3d_reference=reference,
                        run_dir=run_dir,
                        mode_count=mode_count,
                        timeout_seconds=args.timeout_seconds,
                        warning_gib=args.hybrid_warning_gib,
                        terminate_gib=args.hybrid_terminate_gib,
                    ),
                    "run_dir": run_dir,
                }
            )
        hybrid_results = _run_batch(hybrid_jobs, args.max_parallel)
        _append_ledger(ledger, hybrid_results)
        if any(result["status"] == "failed" for result in hybrid_results):
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
