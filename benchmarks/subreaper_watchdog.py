"""Linux whole-workflow watchdog, including orphaned compiler/MPI children.

Run this as a dedicated parent process. Subreaping keeps descendants inside
its tree after intermediate parents exit, including children that call setsid.
The existing process-tree sampler includes this parent in the memory scope.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from benchmarks.task034_wsl_resources import current_cgroup_path, vmstat_swap_pages, wsl_memory_snapshot
from benchmarks.task038_full3d_jit_staging import process_tree_snapshot


def memory_envelope() -> dict:
    memory = wsl_memory_snapshot()
    total, available = memory["mem_total_bytes"], memory["mem_available_bytes"]
    if total is None or available is None:
        raise RuntimeError("physical memory authority unavailable")
    ancestors = []
    path = current_cgroup_path()
    while path is not None and path.is_relative_to('/sys/fs/cgroup'):
        maximum, current = path / 'memory.max', path / 'memory.current'
        if maximum.is_file():
            raw = maximum.read_text().strip()
            if raw != 'max':
                limit, used = int(raw), int(current.read_text())
                total = min(total, limit)
                available = min(available, max(0, limit - used))
                ancestors.append({'path': str(path), 'limit_bytes': limit, 'current_bytes': used})
        if path == Path('/sys/fs/cgroup'):
            break
        path = path.parent
    reserve = max(4 * 1024**3, int(.15 * total))
    return {**memory, 'effective_total_bytes': total,
            'effective_available_bytes': available, 'reserve_bytes': reserve,
            'launch_cap_bytes': min(12_000_000_000, available - reserve),
            'cgroup_limits': ancestors}


def _children() -> dict[int, tuple[int, int]]:
    """Current descendants with (parent, start ticks), excluding this parent."""
    records = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            records[int(entry.name)] = (int(fields[1]), int(fields[19]))
        except (FileNotFoundError, ProcessLookupError):
            continue
    descendants = {os.getpid()}
    while True:
        found = {pid for pid, (ppid, _) in records.items() if ppid in descendants}
        extended = descendants | found
        if extended == descendants:
            break
        descendants = extended
    descendants.remove(os.getpid())
    return {pid: records[pid] for pid in descendants}


def _signal_children(signum: int) -> None:
    # Re-discover every pass: no stale PID may target an unrelated process.
    for pid, identity in _children().items():
        try:
            fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[19]) == identity[1]:
                os.kill(pid, signum)
        except ProcessLookupError:
            pass
        except FileNotFoundError:
            pass


def _reap_adopted(leader_pid: int) -> None:
    for pid, (ppid, _) in _children().items():
        if ppid == os.getpid() and pid != leader_pid:
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass


def _cache_stamp(path: Path | None) -> str:
    """Metadata stability after all descendants are reaped, not a cache hash."""
    digest = hashlib.sha256()
    if path is not None and path.exists():
        for file in sorted(path.rglob('*')):
            try:
                info = file.stat()
                if file.is_file():
                    digest.update(f'{file.relative_to(path)}:{info.st_size}:{info.st_mtime_ns}\n'.encode())
            except FileNotFoundError:
                continue
    return digest.hexdigest()


def supervise(command: list[str], directory: Path, *, wall_seconds: float,
              interval: float = .25, grace_seconds: float = 2.0,
              cache_path: Path | None = None, phase_path: Path | None = None,
              solve_seconds: float | None = None, source_state: dict | None = None) -> dict:
    """Supervise one command, with an explicit workflow wall budget."""
    if not command or min(wall_seconds, interval, grace_seconds) <= 0:
        raise ValueError('command and positive monitoring budgets are required')
    libc = ctypes.CDLL(None, use_errno=True)
    # PR_SET_CHILD_SUBREAPER; Linux-only, intentionally no platform fallback.
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'cannot enable child subreaper')
    if _children():
        raise RuntimeError('watchdog must be a dedicated parent with no existing children')
    directory.mkdir(parents=True, exist_ok=False)
    envelope = memory_envelope()
    cap = envelope['launch_cap_bytes']
    if cap <= 0:
        raise RuntimeError('no safe launch memory budget')
    requested_signal = []
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda value, _frame: requested_signal.append(value))
    started = time.monotonic()
    stop_started = None
    classification = None
    peak_rss = peak_swap = 0
    samples = 0
    stable_since = None
    cache_stamp = None
    observed = set()
    leader = None
    summary = {}
    stage = 'launch'
    swap_baseline = vmstat_swap_pages()
    try:
        with (directory / 'worker.log').open('w') as output, (directory / 'resources.jsonl').open('w') as timeline:
            environment = os.environ.copy()
            if phase_path is not None:
                environment.update(PHYSICAL_WATCHDOG_PARENT_PID=str(os.getpid()),
                                   PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES=str(cap),
                                   PHYSICAL_WATCHDOG_PHASE_PATH=str(phase_path.resolve()))
            leader = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                      start_new_session=True, env=environment)
            while True:
                exit_code = leader.poll()
                _reap_adopted(leader.pid)
                children = _children()
                observed.update(children)
                stage = 'resource_sample'
                sample = process_tree_snapshot(os.getpid(), 'workflow', exit_code)
                current = memory_envelope()
                elapsed = time.monotonic() - started
                phase = json.loads(phase_path.read_text()) if phase_path is not None and phase_path.exists() else {}
                solve_expired = (solve_seconds is not None and phase.get('phase') == 'solve'
                                 and time.monotonic() - phase['phase_started_monotonic'] >= solve_seconds)
                if not sample['all_status_readable']:
                    reason = 'MONITORING_FAILED'
                else:
                    peak_rss = max(peak_rss, sample['rss_bytes'])
                    peak_swap = max(peak_swap, sample['swap_bytes'])
                    reason = (
                        'RESOURCE_CONTROLLED_STOP' if sample['rss_bytes'] >= cap
                        or current['effective_available_bytes'] < current['reserve_bytes']
                        or sample['swap_bytes'] != 0 else
                        'PERFORMANCE_CONTROLLED_STOP' if elapsed >= wall_seconds or solve_expired else
                        'USER_CONTROLLED_STOP' if requested_signal else None)
                sample.update({'elapsed_seconds': elapsed, 'memory_envelope': current,
                               'worker_phase': phase,
                               'launch_cap_bytes': cap, 'warning': peak_rss >= .85 * cap,
                               'live_or_unreaped_children': sorted(children)})
                stage = 'timeline_write'
                timeline.write(json.dumps(sample, allow_nan=False) + '\n')
                timeline.flush()
                samples += 1
                if reason and classification is None:
                    classification, stop_started = reason, time.monotonic()
                if classification is not None and children:
                    signum = signal.SIGTERM if time.monotonic() - stop_started < grace_seconds else signal.SIGKILL
                    _signal_children(signum)
                if exit_code is not None and not children:
                    stage = 'cache_stability'
                    stamp = _cache_stamp(cache_path)
                    if stamp != cache_stamp:
                        cache_stamp, stable_since = stamp, time.monotonic()
                    if time.monotonic() - stable_since >= max(1.0, 2 * interval):
                        classification = classification or ('COMPLETED' if exit_code == 0 else 'WORKER_FAILED')
                        break
                else:
                    stable_since = None
                    cache_stamp = None
                if stop_started is not None and time.monotonic() - stop_started > grace_seconds + 10:
                    raise RuntimeError('descendants did not clear after SIGKILL')
                time.sleep(interval)
        summary['cache_metadata_stable'] = True
    except BaseException as exc:
        classification = 'MONITORING_FAILED'
        summary.update({'exception_stage': stage, 'exception_type': type(exc).__name__,
                        'exception_message': str(exc), 'cache_metadata_stable': False})
    finally:
        # Also close the tree if sampling, JSON writing, or the parent fails.
        deadline = time.monotonic() + grace_seconds + 10
        while leader is not None and _children() and time.monotonic() < deadline:
            _signal_children(signal.SIGKILL)
            leader.poll()
            _reap_adopted(leader.pid)
            time.sleep(.02)
        if leader is not None:
            leader.poll()
        remaining = _children()
        swap_end = vmstat_swap_pages()
        swap_delta = {key: None if swap_baseline[key] is None or swap_end[key] is None
                      else swap_end[key] - swap_baseline[key] for key in swap_baseline}
        summary.update({
            'classification': 'EVIDENCE_INCOMPLETE' if remaining else classification,
            'leader_exit_code': None if leader is None else leader.returncode,
            'descendants_cleared': not remaining, 'remaining_child_pids': sorted(remaining),
            'observed_child_pids': sorted(observed),
            'sampled_process_tree_rss_peak_bytes': peak_rss if samples else None,
            'sampled_process_tree_swap_peak_bytes': peak_swap if samples else None,
            'memory_scope': 'dedicated subreaper parent plus all descendants; sampled simultaneous RSS',
            'swap_scope': 'same process tree sampled VmSwap; no global swap attribution',
            'global_swap_activity': {'scope': 'WSL-global diagnostic, not dedicated job',
                                     'baseline': swap_baseline, 'end': swap_end, 'delta': swap_delta},
            'job_swap_activity': ('zero_supported_by_zero_global_activity' if
                                  all(value == 0 for value in swap_delta.values()) else
                                  'UNRESOLVED_global_activity_cannot_be_attributed'),
            'launch_envelope': envelope, 'samples': samples,
            'elapsed_seconds': time.monotonic() - started,
            'cache_metadata_stamp': cache_stamp,
            'source_state': source_state if source_state is not None else 'development_worktree; not formal PDE provenance',
        })
        (directory / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--wall-seconds', type=float, required=True)
    parser.add_argument('--interval', type=float, default=.25)
    parser.add_argument('--grace-seconds', type=float, default=2)
    parser.add_argument('--cache-path', type=Path)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    summary = supervise(command, args.directory, wall_seconds=args.wall_seconds,
                        interval=args.interval, grace_seconds=args.grace_seconds,
                        cache_path=args.cache_path)
    print(json.dumps(summary, allow_nan=False), flush=True)
    return 0 if summary['classification'] == 'COMPLETED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
