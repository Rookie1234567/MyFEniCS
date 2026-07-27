"""Single-job process-group executor with Linux /proc resource telemetry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Mapping, Sequence


EXIT_CONTROLLED_TIMEOUT = 124
EXIT_CONTROLLED_MEMORY = 125
EXIT_CONTROLLED_SIGNAL_BASE = 128


@dataclass(frozen=True)
class ResourceSample:
    timestamp_utc: str
    elapsed_seconds: float
    stage: str | None
    readable_pids: int
    rss_bytes: int
    pss_bytes: int
    uss_bytes: int
    swap_bytes: int


@dataclass(frozen=True)
class WatchdogResult:
    status: str
    return_code: int
    child_return_code: int | None
    elapsed_seconds: float
    peak_rss_bytes: int
    peak_pss_bytes: int
    peak_uss_bytes: int
    peak_swap_bytes: int
    samples: int
    process_group_id: int
    cleanup_complete: bool


def _proc_table() -> dict[int, int]:
    table: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().split()
            table[int(entry.name)] = int(fields[3])
        except (FileNotFoundError, PermissionError, IndexError, ValueError):
            continue
    return table


def _descendants(root_pid: int) -> set[int]:
    table = _proc_table()
    found = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, ppid in table.items():
            if ppid in found and pid not in found:
                found.add(pid)
                changed = True
    return found


def _memory_for_pid(pid: int) -> tuple[int, int, int, int] | None:
    values: dict[str, int] = {}
    try:
        for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
            key, _, tail = line.partition(":")
            if key in {"Rss", "Pss", "Private_Clean", "Private_Dirty", "Private_Hugetlb", "Swap"}:
                values[key] = int(tail.strip().split()[0]) * 1024
    except (FileNotFoundError, PermissionError, ValueError):
        return None
    uss = sum(values.get(key, 0) for key in ("Private_Clean", "Private_Dirty", "Private_Hugetlb"))
    return values.get("Rss", 0), values.get("Pss", 0), uss, values.get("Swap", 0)


def process_tree_sample(root_pid: int, elapsed: float, stage: str | None = None) -> ResourceSample:
    totals = [0, 0, 0, 0]
    readable = 0
    for pid in _descendants(root_pid):
        observed = _memory_for_pid(pid)
        if observed is None:
            continue
        readable += 1
        for index, value in enumerate(observed):
            totals[index] += value
    return ResourceSample(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=elapsed,
        stage=stage,
        readable_pids=readable,
        rss_bytes=totals[0], pss_bytes=totals[1], uss_bytes=totals[2], swap_bytes=totals[3],
    )


def _current_stage(stage_file: Path | None) -> str | None:
    if stage_file is None or not stage_file.is_file():
        return None
    try:
        lines = [line for line in stage_file.read_text().splitlines() if line.strip()]
        return None if not lines else str(json.loads(lines[-1]).get("stage"))
    except (OSError, ValueError, TypeError):
        return None


def _terminate_group(pgid: int, grace_seconds: float) -> None:
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_with_watchdog(
    command: Sequence[str], *, cwd: Path, env: Mapping[str, str], output_dir: Path,
    timeout_seconds: float, memory_limit_bytes: int, sample_interval_seconds: float = 1.0,
    heartbeat_seconds: float = 30.0, grace_seconds: float = 5.0,
    stage_file: Path | None = None,
) -> WatchdogResult:
    """Run exactly one command and control only its newly created process group."""

    if timeout_seconds <= 0 or memory_limit_bytes <= 0 or sample_interval_seconds <= 0:
        raise ValueError("watchdog timeout, memory limit and sample interval must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / "stdout.log"
    stderr_path = output_dir / "stderr.log"
    timeline_path = output_dir / "resource_timeline.jsonl"
    heartbeat_path = output_dir / "heartbeat.json"
    started = time.monotonic()
    status = "completed"
    effective_code: int | None = None
    samples: list[ResourceSample] = []
    received_signal: int | None = None

    def handle_signal(signum, _frame) -> None:
        nonlocal received_signal
        received_signal = int(signum)

    previous_handlers: dict[int, object] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            previous_handlers[signum] = signal.signal(signum, handle_signal)
        except ValueError:  # non-main-thread library use
            previous_handlers = {}
            break
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            list(command), cwd=cwd, env=dict(env), stdout=stdout, stderr=stderr,
            text=True, start_new_session=True,
        )
        pgid = os.getpgid(process.pid)
        next_heartbeat = started
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - started
                sample = process_tree_sample(process.pid, elapsed, _current_stage(stage_file))
                samples.append(sample)
                with timeline_path.open("a", encoding="utf-8") as timeline:
                    timeline.write(json.dumps(asdict(sample), sort_keys=True) + "\n")
                if time.monotonic() >= next_heartbeat:
                    heartbeat_path.write_text(json.dumps(asdict(sample), indent=2) + "\n")
                    next_heartbeat = time.monotonic() + heartbeat_seconds
                if sample.swap_bytes > 0 or sample.rss_bytes >= memory_limit_bytes:
                    status = "controlled_stop_resource_memory"
                    effective_code = EXIT_CONTROLLED_MEMORY
                    _terminate_group(pgid, grace_seconds)
                    break
                if received_signal is not None:
                    status = "controlled_stop_signal"
                    effective_code = EXIT_CONTROLLED_SIGNAL_BASE + received_signal
                    _terminate_group(pgid, grace_seconds)
                    break
                if elapsed >= timeout_seconds:
                    status = "controlled_stop_timeout"
                    effective_code = EXIT_CONTROLLED_TIMEOUT
                    _terminate_group(pgid, grace_seconds)
                    break
                time.sleep(sample_interval_seconds)
        except BaseException:
            _terminate_group(pgid, grace_seconds)
            process.wait(timeout=max(grace_seconds, 1.0))
            for signum, previous in previous_handlers.items():
                signal.signal(signum, previous)
            raise
        child_code = process.wait()
    for signum, previous in previous_handlers.items():
        signal.signal(signum, previous)
    if effective_code is None:
        effective_code = child_code
        status = "completed" if child_code == 0 else "failed"
    cleanup_complete = not _descendants(process.pid) - {process.pid}
    return WatchdogResult(
        status=status, return_code=effective_code, child_return_code=child_code,
        elapsed_seconds=time.monotonic() - started,
        peak_rss_bytes=max((s.rss_bytes for s in samples), default=0),
        peak_pss_bytes=max((s.pss_bytes for s in samples), default=0),
        peak_uss_bytes=max((s.uss_bytes for s in samples), default=0),
        peak_swap_bytes=max((s.swap_bytes for s in samples), default=0),
        samples=len(samples), process_group_id=pgid, cleanup_complete=cleanup_complete,
    )
