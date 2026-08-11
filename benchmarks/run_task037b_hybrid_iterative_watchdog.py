"""Dedicated resource watchdog for the explicit frozen M10 runner."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _sample,
)
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)
from benchmarks.task037c_robustness import (
    TASK37C_TRACTION_MODELS,
    classify_mpi_resource,
    make_task37c_profile,
)


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_SCHEMA = "task037b.m10-frozen-watchdog.v1"
TASK37C_WATCHDOG_SCHEMA = "task037c.robustness-watchdog.v1"
WORKER_MODULE = "benchmarks.run_task037b_hybrid_iterative"
FROZEN_M10_MPI_SIZE = 8
SAMPLE_INTERVAL_SECONDS = 1.0
HEARTBEAT_SECONDS = 30.0
TIMEOUT_SECONDS = 7200.0
RSS_LIMIT_MIB = 6144.0
SWAP_LIMIT_MIB = 0.0
THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
    "PYTHONUNBUFFERED": "1",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _source_preflight(verified_clean_sha: str) -> dict[str, Any]:
    if len(verified_clean_sha) != 40 or any(
        character not in "0123456789abcdef" for character in verified_clean_sha
    ):
        raise ValueError("verified-clean-sha must be a 40-character lowercase SHA")
    head = _git_value("rev-parse", "HEAD")
    dirty = _git_value("status", "--porcelain", "--untracked-files=all")
    branch = _git_value("branch", "--show-current")
    if head != verified_clean_sha or dirty:
        raise RuntimeError(
            f"source preflight failed: head={head}, verified={verified_clean_sha}, "
            f"dirty={dirty!r}"
        )
    return {
        "head": head,
        "branch": branch,
        "verified_clean_sha": verified_clean_sha,
        "dirty": dirty,
        "clean": True,
        "match": True,
    }


def _authority_binding(
    label: str, path_value: str | Path, expected_sha: str
) -> dict[str, Any]:
    path = Path(path_value).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} authority is not a file: {path}")
    actual_sha = _sha256(path)
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"{label} authority SHA mismatch: expected {expected_sha}, got {actual_sha}"
        )
    return {
        "label": label,
        "path": _display_path(path),
        "sha256": actual_sha,
        "bytes": path.stat().st_size,
        "pass": True,
    }


def _artifact_descriptor(path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value).resolve()
    descriptor: dict[str, Any] = {
        "path": _display_path(path),
        "exists": path.is_file(),
        "bytes": None,
        "sha256": None,
    }
    if descriptor["exists"]:
        descriptor["bytes"] = path.stat().st_size
        descriptor["sha256"] = _sha256(path)
    return descriptor


def _read_online_record(path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value).resolve()
    descriptor = _artifact_descriptor(path)
    if not descriptor["exists"]:
        return {
            "descriptor": descriptor,
            "json_valid": False,
            "record": None,
            "failures": ["online_record_missing"],
        }
    try:
        with path.open(encoding="utf-8") as stream:
            record = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        return {
            "descriptor": descriptor,
            "json_valid": False,
            "record": None,
            "failures": [f"online_record_invalid:{error}"],
        }
    if not isinstance(record, Mapping):
        return {
            "descriptor": descriptor,
            "json_valid": False,
            "record": None,
            "failures": ["online_record_root_not_mapping"],
        }
    return {
        "descriptor": descriptor,
        "json_valid": True,
        "record": dict(record),
        "failures": [],
    }


def _record_paths(value: Any, key: str | None = None) -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            if child_key in {"path", "manifest"} and isinstance(child, str):
                paths.append(child)
            paths.extend(_record_paths(child, str(child_key)))
    elif isinstance(value, list):
        for child in value:
            paths.extend(_record_paths(child, key))
    return paths


def _resolve_record_path(value: str, run_root: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    root_candidate = ROOT / candidate
    if root_candidate.exists():
        return root_candidate
    return run_root / candidate


def _artifact_descriptors(
    run_root: Path,
    online_path: Path,
    memory_stages: Path,
    timeline: Path,
    stdout: Path,
    record: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    paths = [online_path, memory_stages, timeline, stdout]
    if record is not None:
        paths.extend(
            _resolve_record_path(value, run_root) for value in _record_paths(record)
        )
    descriptors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        resolved = str(Path(path).resolve())
        if resolved not in seen:
            descriptors.append(_artifact_descriptor(path))
            seen.add(resolved)
    return descriptors


def build_worker_command(
    args: argparse.Namespace,
    payload_dir: Path,
    online_path: Path,
    memory_stages: Path,
) -> list[str]:
    if args.frozen_m10:
        mpi_size = FROZEN_M10_MPI_SIZE
        profile_args = ["--frozen-m10"]
    else:
        mpi_size = int(args.mpi_size)
        profile_args = [
            "--task037c-robustness-gate",
            "--incident-phi-deg",
            str(args.incident_phi_deg),
            "--requested-modes",
            str(args.requested_modes),
            "--mpi-size",
            str(args.mpi_size),
            "--internal-traction-model",
            args.internal_traction_model,
        ]
        if args.task037c_two_pass_side_correction:
            profile_args.append("--task037c-two-pass-side-correction")
    command = [
        "mpiexec",
        "-n",
        str(mpi_size),
        sys.executable,
        "-m",
        WORKER_MODULE,
        *profile_args,
        "--case-label",
        args.case_label,
        "--run-dir",
        str(payload_dir),
        "--output",
        str(online_path),
        "--memory-stages",
        str(memory_stages),
        "--verified-clean-sha",
        args.verified_clean_sha,
    ]
    if args.frozen_m10:
        command.extend(
            [
                "--h1-authority",
                str(Path(args.h1_authority).resolve()),
                "--h1-authority-sha256",
                args.h1_authority_sha256,
                "--full3d-reference",
                str(Path(args.full3d_reference).resolve()),
                "--full3d-reference-sha256",
                args.full3d_reference_sha256,
                "--task035c-p6-preflight-authority",
                str(Path(args.task035c_p6_preflight_authority).resolve()),
                "--task035c-p6-preflight-sha256",
                args.task035c_p6_preflight_sha256,
            ]
        )
    return command


def _worker_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(THREAD_ENV)
    return environment


def _numeric_row_value(row: Mapping[str, Any], key: str) -> float:
    try:
        value = float(row.get(key, 0.0))
    except (TypeError, ValueError):
        return math.inf
    return value if math.isfinite(value) else math.inf


def _resource_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    profile_kind: str = "frozen_m10",
    mpi_size: int = FROZEN_M10_MPI_SIZE,
    termination_limit: float | None = RSS_LIMIT_MIB,
) -> dict[str, Any]:
    if rows:
        peak_row = max(
            rows,
            key=lambda row: _numeric_row_value(row, "mpi_process_tree_rss_mb"),
        )
    else:
        peak_row = {}
    peak_rss = _numeric_row_value(peak_row, "mpi_process_tree_rss_mb")
    peak_swap = max(
        (_numeric_row_value(row, "mpi_process_tree_swap_mb") for row in rows),
        default=0.0,
    )
    finite_sample = bool(rows) and math.isfinite(peak_rss) and math.isfinite(peak_swap)
    swap_pass = finite_sample and peak_swap == SWAP_LIMIT_MIB
    preferred_pass = finite_sample and peak_rss <= RSS_LIMIT_MIB and swap_pass
    if profile_kind == "frozen_m10":
        resource_pass = preferred_pass
        classification = "preferred" if resource_pass else "resource_unqualified"
    elif int(mpi_size) == 1:
        classification_info = classify_mpi_resource(
            mpi_size=1,
            numerical_pass=True,
            rss_mib=peak_rss,
            swap_mib=peak_swap,
        )
        preferred_pass = bool(classification_info["preferred_pass"])
        resource_pass = (
            finite_sample and swap_pass and not classification_info["hard_stop"]
        )
        classification = str(classification_info["classification"])
    else:
        classification_info = classify_mpi_resource(
            mpi_size=8,
            numerical_pass=True,
            rss_mib=peak_rss,
            swap_mib=peak_swap,
        )
        preferred_pass = bool(classification_info["preferred_pass"])
        resource_pass = finite_sample and swap_pass
        classification = str(classification_info["classification"])
    return {
        "sample_count": len(rows),
        "process_tree_peak_rss_mib": peak_rss,
        "process_tree_peak_stage": peak_row.get("stage"),
        "process_tree_peak_elapsed_seconds": peak_row.get("elapsed_seconds"),
        "process_tree_peak_swap_mib": peak_swap,
        "worker_rank_pss_peak_mib": max(
            (_numeric_row_value(row, "worker_rank_pss_sum_mb") for row in rows),
            default=0.0,
        ),
        "worker_rank_uss_peak_mib": max(
            (_numeric_row_value(row, "worker_rank_uss_sum_mb") for row in rows),
            default=0.0,
        ),
        "rss_limit_mib": RSS_LIMIT_MIB,
        "termination_rss_limit_mib": termination_limit,
        "swap_limit_mib": SWAP_LIMIT_MIB,
        "rss_pass": resource_pass,
        "preferred_pass": preferred_pass,
        "classification": classification,
        "swap_pass": swap_pass,
        "pass": resource_pass,
        "timeline_authority": "simultaneous mpi_process_tree_rss_mb",
    }


def _qualification_summary(
    worker_return_code: int | None,
    online_pass: bool,
    resource: Mapping[str, Any],
    termination_classification: str,
    process_control: Mapping[str, Any],
    *,
    profile_kind: str = "frozen_m10",
    mpi_size: int = FROZEN_M10_MPI_SIZE,
) -> dict[str, Any]:
    checks = {
        "worker_exit0": worker_return_code == 0,
        "online_pass": online_pass is True,
        "resource_pass": resource.get("pass") is True,
        "swap_zero": resource.get("process_tree_peak_swap_mib") == 0.0,
        "no_timeout": termination_classification != "wall_timeout",
        "process_group_clean": (
            process_control.get("worker_exited") is True
            and process_control.get("process_group_exited") is True
        ),
    }
    passed = all(checks.values())
    return {
        "checks": checks,
        "pass": passed,
        "status": ("watchdog_pass_awaiting_offline_checker" if passed else "failed"),
    }


def _write_timeline_row(
    writer: csv.DictWriter[str],
    stream: Any,
    row: Mapping[str, Any],
) -> None:
    writer.writerow({field: row.get(field) for field in TIMELINE_FIELDS})
    stream.flush()


def _sampling_loop(
    process: Any,
    memory_stages: Path,
    writer: csv.DictWriter[str],
    stream: Any,
    *,
    sample_fn: Callable[[int, Path, float], dict[str, Any]] = _sample,
    terminator: Callable[[Any], dict[str, Any]] = terminate_process_tree,
    clock: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
    heartbeat_fn: Callable[[str], None] = print,
    rss_limit: float = RSS_LIMIT_MIB,
    heartbeat_label: str = "M10",
    rss_limit_inclusive: bool = False,
) -> dict[str, Any]:
    started = clock()
    previous: Mapping[str, Any] | None = None
    last_heartbeat = -HEARTBEAT_SECONDS
    rows: list[dict[str, Any]] = []
    termination_classification = "natural_exit"
    termination_reason: str | None = None
    process_control: dict[str, Any] | None = None
    process_control_error: str | None = None
    termination_calls = 0
    while True:
        elapsed = clock() - started
        row = sample_fn(process.pid, memory_stages, elapsed)
        _add_cpu_core_equivalents(row, previous)
        previous = row
        rows.append(row)
        _write_timeline_row(writer, stream, row)
        rss = _numeric_row_value(row, "mpi_process_tree_rss_mb")
        swap = _numeric_row_value(row, "mpi_process_tree_swap_mb")
        if elapsed - last_heartbeat >= HEARTBEAT_SECONDS:
            heartbeat_fn(
                f"{heartbeat_label} watchdog heartbeat "
                f"elapsed={elapsed:.1f}s stage={row.get('stage')} "
                f"process_tree_rss_mib={rss:.3f} swap_mib={swap:.3f}"
            )
            last_heartbeat = elapsed
        return_code = process.poll()
        rss_exceeded = rss >= rss_limit if rss_limit_inclusive else rss > rss_limit
        if rss_exceeded:
            termination_classification = "rss_limit_exceeded"
            termination_reason = f"process_tree_rss_mib={rss}"
        elif swap > SWAP_LIMIT_MIB:
            termination_classification = "swap_detected"
            termination_reason = f"process_tree_swap_mib={swap}"
        elif return_code is not None:
            termination_classification = "natural_exit"
            termination_reason = None
        elif elapsed >= TIMEOUT_SECONDS:
            termination_classification = "wall_timeout"
            termination_reason = f"elapsed_seconds={elapsed}"
        else:
            sleep_fn(SAMPLE_INTERVAL_SECONDS)
            continue
        if termination_calls == 0:
            try:
                process_control = terminator(process)
            except RuntimeError as error:
                process_control_error = str(error)
                process_control = {
                    "worker_exited": False,
                    "process_group_exited": False,
                    "error": process_control_error,
                }
            termination_calls += 1
        break
    return {
        "rows": rows,
        "return_code": process.returncode,
        "termination_classification": termination_classification,
        "termination_reason": termination_reason,
        "process_control": process_control or {},
        "process_control_error": process_control_error,
        "termination_calls": termination_calls,
        "timeout": termination_classification == "wall_timeout",
    }


def _new_paths(
    args: argparse.Namespace,
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    run_root = Path(args.run_root).resolve()
    output = Path(args.output).resolve()
    payload = run_root / "payload"
    online = run_root / "online_record.json"
    memory_stages = run_root / "memory_stages.jsonl"
    timeline = run_root / "memory_timeline.csv"
    stdout = run_root / "worker_stdout.txt"
    if run_root.exists() or output.exists():
        raise FileExistsError("run-root and output must both be absent")
    for path in (payload, online, memory_stages, timeline, stdout):
        if path.exists():
            raise FileExistsError(f"watchdog output collision: {path}")
    return run_root, output, payload, online, memory_stages, timeline, stdout


def _summary_failure(
    output: Path,
    error: Exception,
    *,
    task37c: bool = False,
    profile_id: str | None = None,
) -> int:
    if output.exists():
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": TASK37C_WATCHDOG_SCHEMA if task37c else WATCHDOG_SCHEMA,
        "frozen": not task37c,
        "explicit_opt_in": True,
        "ordinary_default_changed": False,
        "profile": profile_id,
        "qualification": {"pass": False, "checks": {}},
        "status": "failed",
        "failures": [f"watchdog_error:{error}"],
    }
    with output.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return 2


def run_watchdog(args: argparse.Namespace) -> int:
    if args.task037c_robustness_gate:
        profile = make_task37c_profile(
            args.incident_phi_deg,
            args.requested_modes,
            args.mpi_size,
            traction_model=args.internal_traction_model,
            side_residual_correction_steps=(
                2 if args.task037c_two_pass_side_correction else 1
            ),
        )
    else:
        profile = None
    source = _source_preflight(args.verified_clean_sha)
    authorities = []
    if args.frozen_m10:
        authorities = [
            _authority_binding(
                "h1_direct_hybrid", args.h1_authority, args.h1_authority_sha256
            ),
            _authority_binding(
                "full3d_reference",
                args.full3d_reference,
                args.full3d_reference_sha256,
            ),
            _authority_binding(
                "task035c_p6_preflight",
                args.task035c_p6_preflight_authority,
                args.task035c_p6_preflight_sha256,
            ),
        ]
    run_root, output, payload, online, memory_stages, timeline, stdout = _new_paths(
        args
    )
    run_root.mkdir(parents=True, exist_ok=False)
    command = build_worker_command(args, payload, online, memory_stages)
    environment = _worker_environment()
    with (
        stdout.open("w", encoding="utf-8") as stdout_stream,
        timeline.open("w", encoding="utf-8", newline="") as timeline_stream,
    ):
        writer = csv.DictWriter(timeline_stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        timeline_stream.flush()
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout_stream,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            **worker_process_group_popen_kwargs(),
        )
        is_m10 = args.frozen_m10
        mpi_size = FROZEN_M10_MPI_SIZE if is_m10 else int(args.mpi_size)
        profile_kind = "frozen_m10" if is_m10 else "task037c"
        termination_limit = RSS_LIMIT_MIB if is_m10 or mpi_size == 1 else None
        sampling = _sampling_loop(
            process,
            memory_stages,
            writer,
            timeline_stream,
            rss_limit=termination_limit if termination_limit is not None else math.inf,
            heartbeat_label=("M10" if is_m10 else profile.profile_id),
            rss_limit_inclusive=bool(not is_m10 and mpi_size == 1),
        )
    online_state = _read_online_record(online)
    record = online_state["record"]
    resource = _resource_summary(
        sampling["rows"],
        profile_kind=profile_kind,
        mpi_size=mpi_size,
        termination_limit=termination_limit,
    )
    online_pass = bool(
        online_state["json_valid"]
        and record is not None
        and record.get("online_pass") is True
    )
    qualification = _qualification_summary(
        sampling["return_code"],
        online_pass,
        resource,
        sampling["termination_classification"],
        sampling["process_control"],
        profile_kind=profile_kind,
        mpi_size=mpi_size,
    )
    failures = list(online_state["failures"])
    failures.extend(
        key for key, passed in qualification["checks"].items() if not passed
    )
    summary = {
        "schema": WATCHDOG_SCHEMA if is_m10 else TASK37C_WATCHDOG_SCHEMA,
        "frozen": bool(is_m10),
        "explicit_opt_in": True,
        "ordinary_default_changed": False,
        "case_label": args.case_label,
        "source_preflight": source,
        "authority_bindings": authorities,
        "command": {
            "argv": command,
            "shell": shlex.join(command),
            "module": WORKER_MODULE,
            "mpi_size": FROZEN_M10_MPI_SIZE if args.frozen_m10 else args.mpi_size,
            "profile": None if profile is None else profile.profile_id,
        },
        "environment": {
            "python_executable": sys.executable,
            "fixed": dict(THREAD_ENV),
        },
        "worker": {"return_code": sampling["return_code"]},
        "termination": {
            "classification": sampling["termination_classification"],
            "reason": sampling["termination_reason"],
            "process_control": sampling["process_control"],
            "process_control_error": sampling["process_control_error"],
            "termination_calls": sampling["termination_calls"],
        },
        "artifacts": _artifact_descriptors(
            run_root, online, memory_stages, timeline, stdout, record
        ),
        "resource": resource,
        "online_record": {
            "path": online_state["descriptor"]["path"],
            "sha256": online_state["descriptor"]["sha256"],
            "json_valid": online_state["json_valid"],
            "status": record.get("status") if record else None,
            "online_pass": online_pass,
        },
        "qualification": qualification,
        "failures": failures,
        "status": qualification["status"],
        "profile": None if profile is None else profile.__dict__,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return 0 if qualification["pass"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    profile_group = parser.add_mutually_exclusive_group(required=True)
    profile_group.add_argument("--frozen-m10", action="store_true")
    profile_group.add_argument("--task037c-robustness-gate", action="store_true")
    parser.add_argument("--case-label", required=True)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--h1-authority", type=Path)
    parser.add_argument("--h1-authority-sha256")
    parser.add_argument("--full3d-reference", type=Path)
    parser.add_argument("--full3d-reference-sha256")
    parser.add_argument("--task035c-p6-preflight-authority", type=Path)
    parser.add_argument("--task035c-p6-preflight-sha256")
    parser.add_argument("--incident-phi-deg", type=float, choices=(-5.0, 0.0, 5.0))
    parser.add_argument("--requested-modes", type=int, choices=(120, 160))
    parser.add_argument("--mpi-size", type=int, choices=(1, 8))
    parser.add_argument(
        "--internal-traction-model",
        choices=TASK37C_TRACTION_MODELS,
        default=None,
    )
    parser.add_argument(
        "--task037c-two-pass-side-correction",
        action="store_true",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.task037c_robustness_gate:
        if args.incident_phi_deg is None or args.requested_modes is None:
            parser.error("Task37c requires phi and requested modes")
        if args.mpi_size is None:
            parser.error("Task37c requires --mpi-size")
        if any(
            value is not None
            for value in (
                args.h1_authority,
                args.h1_authority_sha256,
                args.full3d_reference,
                args.full3d_reference_sha256,
                args.task035c_p6_preflight_authority,
                args.task035c_p6_preflight_sha256,
            )
        ):
            parser.error("Task37c does not accept Task37b authority arguments")
        args.internal_traction_model = (
            args.internal_traction_model or TASK37C_TRACTION_MODELS[0]
        )
    else:
        if args.task037c_two_pass_side_correction:
            parser.error("frozen M10 does not accept two-pass side correction")
        if args.internal_traction_model is not None:
            parser.error("frozen M10 does not accept --internal-traction-model")
        if any(
            value is not None
            for value in (args.incident_phi_deg, args.requested_modes, args.mpi_size)
        ):
            parser.error("Task37b frozen M10 does not accept Task37c options")
        required_authorities = (
            args.h1_authority,
            args.h1_authority_sha256,
            args.full3d_reference,
            args.full3d_reference_sha256,
            args.task035c_p6_preflight_authority,
            args.task035c_p6_preflight_sha256,
        )
        if any(value is None for value in required_authorities):
            parser.error("frozen M10 requires all authority path/hash pairs")
        args.internal_traction_model = TASK37C_TRACTION_MODELS[0]
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run_watchdog(args)
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        label = (
            "Task37c robustness watchdog"
            if args.task037c_robustness_gate
            else "M10 watchdog"
        )
        print(f"{label} failed closed: {error}", file=sys.stderr)
        return _summary_failure(
            Path(args.output).resolve(),
            error,
            task37c=args.task037c_robustness_gate,
            profile_id=(
                "task037c.robustness.grazing1.v1"
                if args.task037c_robustness_gate
                else "task037b.m10.frozen.p6-h10.v1"
            ),
        )


if __name__ == "__main__":
    raise SystemExit(main())
