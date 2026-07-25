from __future__ import annotations

import argparse
import csv
import json
import os
import queue
import re
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from ..common.config_3d import project_root


BYTES_PER_GB = 1024.0**3
KB_PER_GB = 1024.0**2


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _tail_join(lines: deque[str], *, max_chars: int = 4000) -> str:
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[-max_chars:]
    return text


def _read_stream(stream, output_path: Path, lines: deque[str], notifications: queue.Queue[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", errors="ignore") as fp:
        for line in iter(stream.readline, ""):
            fp.write(line)
            fp.flush()
            stripped = line.rstrip("\n")
            lines.append(stripped)
            notifications.put(stripped)
    stream.close()


def _children_of(pid: int) -> list[int]:
    path = Path(f"/proc/{pid}/task/{pid}/children")
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return []
    if not text:
        return []
    children: list[int] = []
    for token in text.split():
        try:
            children.append(int(token))
        except ValueError:
            continue
    return children


def _process_tree(root_pid: int) -> list[int]:
    seen: set[int] = set()
    stack = [root_pid]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        if not Path(f"/proc/{pid}").exists():
            continue
        seen.add(pid)
        stack.extend(_children_of(pid))
    return sorted(seen)


def _terminate_process_tree(root_pid: int) -> None:
    pids = list(reversed(_process_tree(root_pid)))
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in pids:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                continue
            except OSError:
                continue
        time.sleep(0.5)


def _rss_kb(pid: int) -> float | None:
    status = Path(f"/proc/{pid}/status")
    try:
        lines = status.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return float(parts[1])
                except ValueError:
                    return None
    return None


def _rss_stats(pids: list[int]) -> dict[str, Any]:
    values = [value / KB_PER_GB for pid in pids if (value := _rss_kb(pid)) is not None]
    if not values:
        return {
            "num_processes": 0,
            "rss_sum_GB": 0.0,
            "rss_max_GB": 0.0,
            "rss_mean_GB": 0.0,
            "rss_min_GB": 0.0,
        }
    return {
        "num_processes": len(values),
        "rss_sum_GB": float(sum(values)),
        "rss_max_GB": float(max(values)),
        "rss_mean_GB": float(sum(values) / len(values)),
        "rss_min_GB": float(min(values)),
    }


def _swap_used_gb() -> float | None:
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
            values[key] = float(parts[0]) / KB_PER_GB
        except ValueError:
            continue
    if "SwapTotal" not in values or "SwapFree" not in values:
        return None
    return max(values["SwapTotal"] - values["SwapFree"], 0.0)


def _directory_size_gb(path: Path | None) -> float:
    if path is None or not path.exists():
        return 0.0
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            file_path = Path(root) / name
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return float(total / BYTES_PER_GB)


def _last_progress_stage(progress_file: Path | None) -> str:
    if progress_file is None or not progress_file.exists():
        return ""
    last_stage = ""
    try:
        for line in progress_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            stage = payload.get("stage")
            status = payload.get("status")
            if stage:
                last_stage = f"{stage}:{status}" if status else str(stage)
    except OSError:
        return last_stage
    return last_stage


def _extract_result_dir(line: str) -> Path | None:
    match = re.search(r"3D case (?:output directory|results):\s*(.+)", line)
    if not match:
        return None
    return Path(match.group(1).strip())


def _write_csv_row(path: Path, fieldnames: list[str], row: dict[str, Any]) -> None:
    exists = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def _monitor(
    *,
    proc: subprocess.Popen,
    interval_seconds: float,
    timeseries_csv: Path,
    stdout_tail: deque[str],
    stderr_tail: deque[str],
    notifications: queue.Queue[str],
    explicit_progress_file: Path | None,
    explicit_ooc_dir: Path | None,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    fieldnames = [
        "timestamp_s",
        "elapsed_s",
        "stage",
        "status",
        "num_processes",
        "rss_sum_GB",
        "rss_max_GB",
        "rss_mean_GB",
        "rss_min_GB",
        "swap_used_GB",
        "ooc_disk_GB",
        "stdout_tail",
        "stderr_tail",
    ]
    started = time.time()
    result_dir: Path | None = None
    progress_file = explicit_progress_file
    ooc_dir = explicit_ooc_dir
    peak: dict[str, Any] = {
        "peak_rss_sum_GB": 0.0,
        "peak_rss_max_GB": 0.0,
        "peak_ooc_disk_GB": 0.0,
        "peak_swap_used_GB": 0.0,
        "last_stage": "",
        "result_dir": "",
    }
    while True:
        while True:
            try:
                line = notifications.get_nowait()
            except queue.Empty:
                break
            found = _extract_result_dir(line)
            if found is not None:
                result_dir = found
                if progress_file is None:
                    progress_file = result_dir / "progress_3d.jsonl"
                if ooc_dir is None:
                    ooc_dir = result_dir / "mumps_ooc_files"

        elapsed = time.time() - started
        pids = _process_tree(proc.pid)
        rss = _rss_stats(pids)
        swap = _swap_used_gb()
        ooc_disk = _directory_size_gb(ooc_dir)
        stage = _last_progress_stage(progress_file)
        status = "running" if proc.poll() is None else "finished"
        row = {
            "timestamp_s": time.time(),
            "elapsed_s": elapsed,
            "stage": stage,
            "status": status,
            **rss,
            "swap_used_GB": swap,
            "ooc_disk_GB": ooc_disk,
            "stdout_tail": _tail_join(stdout_tail, max_chars=1000),
            "stderr_tail": _tail_join(stderr_tail, max_chars=1000),
        }
        _write_csv_row(timeseries_csv, fieldnames, row)
        peak["peak_rss_sum_GB"] = max(float(peak["peak_rss_sum_GB"]), float(rss["rss_sum_GB"]))
        peak["peak_rss_max_GB"] = max(float(peak["peak_rss_max_GB"]), float(rss["rss_max_GB"]))
        peak["peak_ooc_disk_GB"] = max(float(peak["peak_ooc_disk_GB"]), float(ooc_disk))
        if swap is not None:
            peak["peak_swap_used_GB"] = max(float(peak["peak_swap_used_GB"]), float(swap))
        if stage:
            peak["last_stage"] = stage
        if result_dir is not None:
            peak["result_dir"] = str(result_dir)

        if timeout_seconds is not None and status == "running" and elapsed >= timeout_seconds:
            _terminate_process_tree(proc.pid)
            peak["timed_out"] = True
        if status != "running":
            break
        time.sleep(max(interval_seconds, 0.2))
    peak["elapsed_s"] = time.time() - started
    return peak


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monitor a 3D run subprocess tree RSS/OOC usage.")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--progress-file", default=None)
    parser.add_argument("--ooc-dir", default=None)
    parser.add_argument("--label", default="memory_profile")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("Pass the monitored command after --.")

    root = project_root()
    out_dir = Path(args.output_dir) if args.output_dir else root / "results" / f"memory_profile_{_timestamp()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    timeseries_csv = out_dir / "memory_profile_timeseries.csv"
    summary_csv = out_dir / "memory_profile_summary.csv"
    stdout_file = out_dir / "stdout.txt"
    stderr_file = out_dir / "stderr.txt"

    stdout_tail: deque[str] = deque(maxlen=40)
    stderr_tail: deque[str] = deque(maxlen=40)
    notifications: queue.Queue[str] = queue.Queue()
    proc = subprocess.Popen(
        command,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    threads = [
        threading.Thread(
            target=_read_stream,
            args=(proc.stdout, stdout_file, stdout_tail, notifications),
            daemon=True,
        ),
        threading.Thread(
            target=_read_stream,
            args=(proc.stderr, stderr_file, stderr_tail, notifications),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()
    peak = _monitor(
        proc=proc,
        interval_seconds=args.interval_seconds,
        timeseries_csv=timeseries_csv,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
        notifications=notifications,
        explicit_progress_file=Path(args.progress_file) if args.progress_file else None,
        explicit_ooc_dir=Path(args.ooc_dir) if args.ooc_dir else None,
        timeout_seconds=args.timeout_seconds,
    )
    returncode = proc.wait()
    for thread in threads:
        thread.join(timeout=2.0)
    status = "timeout" if peak.get("timed_out") else "completed" if returncode == 0 else "failed"
    summary = {
        "label": args.label,
        "status": status,
        "returncode": returncode,
        "command": " ".join(command),
        "timeseries_csv": str(timeseries_csv),
        "stdout_file": str(stdout_file),
        "stderr_file": str(stderr_file),
        "stdout_tail": _tail_join(stdout_tail),
        "stderr_tail": _tail_join(stderr_tail),
        **peak,
    }
    fieldnames = list(summary.keys())
    _write_csv_row(summary_csv, fieldnames, summary)
    (out_dir / "memory_profile_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[memory-profile] summary CSV: {summary_csv}")
    print(f"[memory-profile] timeseries CSV: {timeseries_csv}")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
