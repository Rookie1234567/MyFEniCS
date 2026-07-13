from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "benchmarks" / "artifacts" / "cases" / "050"
REFERENCE_RECORDS = {
    5.0: ROOT / "benchmarks" / "records" / "direct_p2_h5_mpi4.json",
    3.0: ROOT / "benchmarks" / "records" / "direct_p2_h3_mpi4.json",
    2.0: ROOT / "benchmarks" / "records" / "direct_p2_h2_reviewed_reference.json",
}
TIMELINE_FIELDS = (
    "timestamp_utc",
    "elapsed_seconds",
    "stage",
    "stage_status",
    "worker_rank_rss_sum_mb",
    "mpi_process_tree_rss_mb",
    "container_process_rss_sum_mb",
    "worker_rank_rss_mb_json",
    "container_cgroup_current_mb",
    "container_cgroup_peak_mb",
    "container_swap_current_mb",
    "wsl_pswpin_pages",
    "wsl_pswpout_pages",
)


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_provenance(args: argparse.Namespace) -> dict[str, Any]:
    """Verify source cleanliness without misreading Windows CRLF in Linux."""

    head = _git("rev-parse", "HEAD")
    if head is None:
        raise SystemExit("Cannot resolve the source commit with git.")
    if args.verified_clean_sha is not None:
        verified = args.verified_clean_sha.strip().lower()
        if len(verified) != 40 or any(
            char not in "0123456789abcdef" for char in verified
        ):
            raise SystemExit(
                "Host clean-source attestation must be a full 40-character Git SHA."
            )
        if head.lower() != verified:
            raise SystemExit(
                "Host clean-source attestation does not match the mounted checkout: "
                f"expected {verified}, mounted HEAD is {head}."
            )
        return {
            "commit_sha": head,
            "tracked_source_dirty": False,
            "tracked_source_verification": "host_git_clean_attestation",
            "verified_clean_sha": verified,
        }

    tracked_status = _git("status", "--porcelain", "--untracked-files=no")
    if tracked_status is None:
        raise SystemExit("Cannot verify tracked-source cleanliness with git.")
    if tracked_status:
        raise SystemExit(
            "Tracked source is dirty. Commit telemetry/candidate code before baseline runs."
        )
    return {
        "commit_sha": head,
        "tracked_source_dirty": False,
        "tracked_source_verification": "local_git_status",
        "verified_clean_sha": None,
    }


def _read_number(path: Path, *, scale: float = 1.0) -> float | str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if value == "max":
        return value
    try:
        return float(value) / scale
    except ValueError:
        return None


def _cgroup_snapshot() -> dict[str, float | str | None]:
    root = Path("/sys/fs/cgroup")
    scale = 1024.0 * 1024.0
    return {
        "container_cgroup_current_mb": _read_number(
            root / "memory.current", scale=scale
        ),
        "container_cgroup_peak_mb": _read_number(root / "memory.peak", scale=scale),
        "container_swap_current_mb": _read_number(
            root / "memory.swap.current", scale=scale
        ),
    }


def _vmstat_swap_pages() -> tuple[int | None, int | None]:
    path = Path("/proc/vmstat")
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None, None
    values: dict[str, int] = {}
    for line in lines:
        parts = line.split()
        if len(parts) == 2 and parts[0] in {"pswpin", "pswpout"}:
            try:
                values[parts[0]] = int(parts[1])
            except ValueError:
                pass
    return values.get("pswpin"), values.get("pswpout")


def _read_processes() -> dict[int, dict[str, Any]]:
    processes: dict[int, dict[str, Any]] = {}
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            status_lines = (
                (entry / "status")
                .read_text(encoding="utf-8", errors="ignore")
                .splitlines()
            )
        except OSError:
            continue
        fields: dict[str, str] = {}
        for line in status_lines:
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key] = value.strip()
        try:
            ppid = int(fields.get("PPid", "0"))
        except ValueError:
            ppid = 0
        rss_parts = fields.get("VmRSS", "0 kB").split()
        try:
            rss_mb = float(rss_parts[0]) / 1024.0
        except (ValueError, IndexError):
            rss_mb = 0.0
        try:
            cmdline = (
                (entry / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", errors="ignore")
            )
        except OSError:
            cmdline = ""
        rank: int | None = None
        if "--worker" in cmdline:
            try:
                environment = (entry / "environ").read_bytes().split(b"\0")
            except OSError:
                environment = []
            for item in environment:
                for key in (
                    b"OMPI_COMM_WORLD_RANK=",
                    b"PMI_RANK=",
                    b"PMIX_RANK=",
                ):
                    if item.startswith(key):
                        try:
                            rank = int(item[len(key) :])
                        except ValueError:
                            rank = None
                        break
                if rank is not None:
                    break
        processes[pid] = {
            "pid": pid,
            "ppid": ppid,
            "rss_mb": rss_mb,
            "cmdline": cmdline,
            "worker_rank": rank,
        }
    return processes


def _descendants(processes: dict[int, dict[str, Any]], root_pid: int) -> set[int]:
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, item in processes.items():
            if pid not in selected and item["ppid"] in selected:
                selected.add(pid)
                changed = True
    return selected


def _latest_stage(progress_path: Path) -> tuple[str, str]:
    try:
        lines = progress_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "process_start", "waiting_for_progress"
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        return str(payload.get("stage", "unknown")), str(
            payload.get("status", "unknown")
        )
    return "process_start", "waiting_for_progress"


def _sample(root_pid: int, progress_path: Path, elapsed: float) -> dict[str, Any]:
    processes = _read_processes()
    tree = _descendants(processes, root_pid)
    worker_ranks = sorted(
        (
            {
                "rank": item["worker_rank"],
                "pid": item["pid"],
                "rss_mb": item["rss_mb"],
            }
            for item in processes.values()
            if item["worker_rank"] is not None
        ),
        key=lambda item: (item["rank"], item["pid"]),
    )
    stage, stage_status = _latest_stage(progress_path)
    pswpin, pswpout = _vmstat_swap_pages()
    row: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "stage": stage,
        "stage_status": stage_status,
        "worker_rank_rss_sum_mb": sum(item["rss_mb"] for item in worker_ranks),
        "mpi_process_tree_rss_mb": sum(
            processes[pid]["rss_mb"] for pid in tree if pid in processes
        ),
        "container_process_rss_sum_mb": sum(
            item["rss_mb"] for item in processes.values()
        ),
        "worker_rank_rss_mb_json": json.dumps(worker_ranks, separators=(",", ":")),
        "wsl_pswpin_pages": pswpin,
        "wsl_pswpout_pages": pswpout,
    }
    row.update(_cgroup_snapshot())
    return row


def _stage_peaks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["stage"]), []).append(row)
    return [
        {
            "stage": stage,
            "samples": len(stage_rows),
            "max_worker_rank_rss_sum_mb": max(
                float(row["worker_rank_rss_sum_mb"]) for row in stage_rows
            ),
            "max_mpi_process_tree_rss_mb": max(
                float(row["mpi_process_tree_rss_mb"]) for row in stage_rows
            ),
            "max_container_cgroup_current_mb": max(
                float(row["container_cgroup_current_mb"] or 0.0) for row in stage_rows
            ),
        }
        for stage, stage_rows in grouped.items()
    ]


def _read_progress_events(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _factor_inventory_from_progress(events: list[dict[str, Any]]) -> Any:
    for event in reversed(events):
        if event.get("stage") == "after_ksp_setup_factorized":
            return event.get("factor_inventory")
    return None


def _task28_reference(h_nm: float) -> dict[str, Any]:
    path = REFERENCE_RECORDS[h_nm]
    return json.loads(path.read_text(encoding="utf-8"))


def _numeric_gate(
    solver_summary: dict[str, Any], reference: dict[str, Any], return_code: int
) -> dict[str, Any]:
    tolerance = 1.0e-8
    deltas: dict[str, float | None] = {}
    for key in ("R_total", "T_total", "A_volume_total"):
        actual = solver_summary.get(key)
        expected = reference.get(key)
        deltas[key] = (
            None
            if actual is None or expected is None
            else float(actual) - float(expected)
        )
    residual = solver_summary.get("linear_system_relative_residual")
    closure = solver_summary.get("energy_closure_error_port_volume")
    checks = {
        "process_completed": return_code == 0,
        "true_residual_le_1e-8": residual is not None and float(residual) <= tolerance,
        "reference_rta_abs_delta_le_1e-8": all(
            value is not None and abs(value) <= tolerance for value in deltas.values()
        ),
        "energy_closure_abs_le_1e-8": closure is not None
        and abs(float(closure)) <= tolerance,
    }
    return {
        "status": "pass" if all(checks.values()) else "failed",
        "checks": checks,
        "task28_reference_delta": deltas,
        "tolerance": tolerance,
    }


def _worker(args: argparse.Namespace) -> int:
    from src.common.config_3d import target_stage4_config
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    extra_options = json.loads(args.petsc_options_json)
    cfg = target_stage4_config(degree=2, h_nm=args.h_nm)
    cfg = replace(
        cfg,
        petsc_direct_solver_profile=args.profile,
        petsc_extra_options=extra_options,
        unique_output=False,
    )
    run_stage4b_block_grating_3d_case(cfg, args.run_dir)
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run and sample Task029 Stage4 direct-memory candidates."
    )
    parser.add_argument("--h-nm", type=float, choices=(5.0, 3.0, 2.0), required=True)
    parser.add_argument("--mpi-size", type=int, default=4)
    parser.add_argument(
        "--profile", choices=("default", "mumps_ooc", "mumps_blr"), default="default"
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--petsc-options-json", default="{}")
    parser.add_argument("--h2-gate-json", type=Path)
    parser.add_argument(
        "--verified-clean-sha",
        default=os.environ.get("TASK029_VERIFIED_CLEAN_SHA"),
        help=(
            "Clean HEAD attested by the host immediately before a Docker bind-mount run; "
            "avoids Linux Git treating Windows CRLF as source edits."
        ),
    )
    parser.add_argument("--worker", action="store_true")
    return parser.parse_args(argv)


def _validate_h2_gate(args: argparse.Namespace) -> None:
    if args.h_nm != 2.0:
        return
    if args.h2_gate_json is None or not args.h2_gate_json.is_file():
        raise SystemExit("h=2 is locked: provide a passing --h2-gate-json record.")
    gate = json.loads(args.h2_gate_json.read_text(encoding="utf-8"))
    required = (
        "h5_numeric_pass",
        "h3_numeric_pass",
        "h5_memory_reduction_20pct",
        "h3_memory_reduction_20pct",
        "h3_no_swap",
        "prediction_upper_le_13p5_gb",
        "watchdog_enabled",
    )
    failed = [key for key in required if gate.get(key) is not True]
    if failed:
        raise SystemExit(f"h=2 remains locked; failed gates: {failed}")


def _run_parent(args: argparse.Namespace) -> int:
    _validate_h2_gate(args)
    source_provenance = _source_provenance(args)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.run_dir or (
        args.artifact_root
        / f"h{args.h_nm:g}_{args.profile}_mpi{args.mpi_size}_{timestamp}"
    )
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    progress_path = run_dir / "progress_3d.jsonl"
    timeline_path = run_dir / "memory_timeline.csv"
    stdout_path = run_dir / "worker_stdout.txt"
    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_direct_memory_forensics",
        "--worker",
        "--h-nm",
        str(args.h_nm),
        "--profile",
        args.profile,
        "--run-dir",
        str(run_dir),
        "--petsc-options-json",
        args.petsc_options_json,
    ]
    worker_environment = os.environ.copy()
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        worker_environment[key] = "1"
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=worker_environment,
        )
        last_stage = ""
        while True:
            row = _sample(process.pid, progress_path, time.perf_counter() - started)
            rows.append(row)
            if row["stage"] != last_stage:
                (run_dir / "memory_stage.txt").write_text(
                    f"{row['stage']} {row['stage_status']}\n", encoding="utf-8"
                )
                last_stage = str(row["stage"])
            if process.poll() is not None:
                break
            time.sleep(max(args.poll_interval, 0.05))
        return_code = int(process.returncode or 0)

    with timeline_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    summary_path = run_dir / "run_summary.json"
    solver_summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.is_file()
        else {}
    )
    progress_events = _read_progress_events(progress_path)
    factor_inventory = _factor_inventory_from_progress(progress_events)
    reference = _task28_reference(args.h_nm)
    numeric_gate = _numeric_gate(solver_summary, reference, return_code)
    extra_options = json.loads(args.petsc_options_json)
    pswpin_values = [
        int(row["wsl_pswpin_pages"])
        for row in rows
        if row.get("wsl_pswpin_pages") is not None
    ]
    pswpout_values = [
        int(row["wsl_pswpout_pages"])
        for row in rows
        if row.get("wsl_pswpout_pages") is not None
    ]
    sampler_summary = {
        "poll_interval_seconds": args.poll_interval,
        "sample_count": len(rows),
        "max_simultaneous_total_rss_mb": max(
            (float(row["worker_rank_rss_sum_mb"]) for row in rows), default=0.0
        ),
        "max_mpi_process_tree_rss_mb": max(
            (float(row["mpi_process_tree_rss_mb"]) for row in rows), default=0.0
        ),
        "max_container_process_rss_sum_mb": max(
            (float(row["container_process_rss_sum_mb"]) for row in rows),
            default=0.0,
        ),
        "max_container_cgroup_current_mb": max(
            (float(row["container_cgroup_current_mb"] or 0.0) for row in rows),
            default=0.0,
        ),
        "container_cgroup_peak_mb_at_end": (
            rows[-1].get("container_cgroup_peak_mb") if rows else None
        ),
        "wsl_pswpin_delta_pages": (
            max(pswpin_values) - min(pswpin_values) if pswpin_values else None
        ),
        "wsl_pswpout_delta_pages": (
            max(pswpout_values) - min(pswpout_values) if pswpout_values else None
        ),
        "stage_peaks": _stage_peaks(rows),
        "timeline": str(timeline_path.relative_to(ROOT)),
    }
    (run_dir / "memory_sampler_summary.json").write_text(
        json.dumps(sampler_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    matrix_transform = solver_summary.get("constraint_matrix_transform") or {}
    record = {
        "benchmark_id": (
            f"task029_direct_h{args.h_nm:g}_{args.profile}_mpi{args.mpi_size}"
        ),
        "status": numeric_gate["status"],
        "metadata": {
            "commit_sha": source_provenance["commit_sha"],
            "branch": _git("branch", "--show-current"),
            "tracked_source_dirty": source_provenance["tracked_source_dirty"],
            "tracked_source_verification": source_provenance[
                "tracked_source_verification"
            ],
            "verified_clean_sha": source_provenance["verified_clean_sha"],
            "timestamp_utc": timestamp,
            "command": command,
            "container_image": os.environ.get(
                "TASK029_CONTAINER_IMAGE", "myfenics-stage4:task28"
            ),
            "container_digest": os.environ.get(
                "TASK029_CONTAINER_DIGEST",
                "sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d",
            ),
            "provenance": "task029_external_sampler_full_direct_run",
        },
        "h_nm": args.h_nm,
        "mpi_size": args.mpi_size,
        "thread_count_per_rank": int(worker_environment["OMP_NUM_THREADS"]),
        "cpu_count_visible": os.cpu_count(),
        "thread_environment": {
            key: worker_environment[key]
            for key in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
        "solver_profile": args.profile,
        "solver_package": solver_summary.get("actual_pc_factor_solver_type"),
        "ordering": extra_options.get(
            "mat_mumps_icntl_7", "backend_default_not_reported"
        ),
        "petsc_options": extra_options,
        "mumps_telemetry": {
            "profile": args.profile,
            "ooc_requested": args.profile == "mumps_ooc",
            "blr_requested": args.profile == "mumps_blr",
            "raw_api_available": None
            if factor_inventory is None
            else factor_inventory.get("mumps_api_available"),
            "raw_infog": None
            if factor_inventory is None
            else factor_inventory.get("mumps_raw_infog"),
            "raw_rinfog": None
            if factor_inventory is None
            else factor_inventory.get("mumps_raw_rinfog"),
        },
        "physical_model": solver_summary.get("config"),
        "resolved_config": solver_summary.get("config"),
        "n_fe": solver_summary.get("num_nedelec_dofs"),
        "n_aux": solver_summary.get("stage4_dtn_num_auxiliary_dofs"),
        "matrix_inventory": {
            "base": solver_summary.get("stage4_dtn_base_matrix_stats"),
            "augmented": solver_summary.get(
                "stage4_dtn_augmented_matrix_stats_after_finalize"
            ),
            "final": solver_summary.get("matrix_stats"),
            "transform": matrix_transform,
        },
        "factor_inventory": factor_inventory,
        "memory_checkpoints": progress_events,
        "memory": {
            **sampler_summary,
            "sum_rank_historical_peaks_mb_upper_bound": solver_summary.get(
                "sum_rank_historical_peaks_mb_upper_bound",
                solver_summary.get("total_peak_rss_mb"),
            ),
        },
        "timings": solver_summary.get("timings_seconds"),
        "true_residual": solver_summary.get("linear_system_relative_residual"),
        "official_rta": {
            "R_total": solver_summary.get("R_total"),
            "T_total": solver_summary.get("T_total"),
            "A_volume_total": solver_summary.get("A_volume_total"),
            "energy_closure_error": solver_summary.get(
                "energy_closure_error_port_volume"
            ),
        },
        "modal_identity": {
            "order_policy": solver_summary.get("stage4_dtn_order_policy"),
            "n_aux": solver_summary.get("stage4_dtn_num_auxiliary_dofs"),
            "top_modes": solver_summary.get("dtn_port_top_mode_count"),
            "bottom_modes": solver_summary.get("dtn_port_bottom_mode_count"),
            "propagating_modes": solver_summary.get("dtn_port_propagating_mode_count"),
        },
        "task28_reference": {
            "benchmark_id": reference.get("benchmark_id"),
            "commit_sha": (reference.get("metadata") or {}).get("commit_sha"),
            "R_total": reference.get("R_total"),
            "T_total": reference.get("T_total"),
            "A_volume_total": reference.get("A_volume_total"),
        },
        "task28_reference_delta": numeric_gate["task28_reference_delta"],
        "qualification": numeric_gate,
        "return_code": return_code,
        "run_directory": str(run_dir.relative_to(ROOT)),
        "limitations": [
            "External sampler reports the simultaneous sum of worker-rank RSS separately from cgroup memory and historical per-rank peaks.",
            "MUMPS INFOG/RINFOG values are raw indexed telemetry without inferred semantics.",
        ],
    }
    record_path = args.record or (run_dir / "candidate_record.json")
    if not record_path.is_absolute():
        record_path = ROOT / record_path
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return return_code


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.worker:
        if args.run_dir is None:
            raise SystemExit("--worker requires --run-dir")
        return _worker(args)
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
