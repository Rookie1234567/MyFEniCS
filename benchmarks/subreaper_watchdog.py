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
from src.runners.workflow_timebase import (TimebaseInconsistency, budget_elapsed,
    clock_info, clock_sample, ClockBudget, STRICT, POLICY_VERSION)


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
    cap = min(12_000_000_000, available - reserve)
    planning = cap
    native = os.environ.get('PHYSICAL_NATIVE_CAPACITY')
    if native:
        from src.io.native_capacity_profile import native_profile_facts
        policy = native_profile_facts(native)['resources']
        reserve = max(policy['reserve_min_bytes'], int(.15 * total))
        cap = min(policy['absolute_cap_bytes'], int(.80 * total), available-reserve)
        planning = min(policy['planning_cap_bytes'], int(.75 * total), cap)
    return {**memory, 'effective_total_bytes': total,
            'effective_available_bytes': available, 'reserve_bytes': reserve,
            'launch_cap_bytes': cap, 'planning_cap_bytes': planning,
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


def _request_cooperative_stop(phase: dict, leader_pid: int) -> dict:
    """Signal the registered application once, never its MPI launcher."""
    worker = phase.get('application_worker', {})
    pid, ticks = worker.get('pid'), worker.get('start_ticks')
    children = _children()
    if (not isinstance(pid, int) or not isinstance(ticks, int) or pid == leader_pid
            or pid not in children or children[pid][1] != ticks):
        raise RuntimeError('cooperative application identity is not in the current child tree')
    current = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    if int(current[19]) != ticks:
        raise RuntimeError('cooperative application identity changed before signal')
    os.kill(pid, signal.SIGTERM)
    return dict(worker_pid=pid, start_ticks=ticks, signal='SIGTERM', request_count=1,
                monotonic=time.monotonic(), timestamp_ns=time.time_ns())


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


def global_swap_stop(baseline, current, *, enabled=False):
    """V6 opt-in: global activity stops pressure without claiming attribution."""
    if not enabled:
        return None
    if any(baseline.get(k) is None or current.get(k) is None for k in baseline):
        return 'MONITORING_FAILED'
    if any(current[k] > baseline[k] for k in baseline):
        return 'GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED'
    return None


def stop_signal(reason, *, hard_stop_immediate, elapsed, grace_seconds):
    hard = hard_stop_immediate and reason in ('RESOURCE_CONTROLLED_STOP', 'MONITORING_FAILED', 'TIMEBASE_INCONSISTENCY', 'GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED')
    return signal.SIGTERM if not hard and elapsed < grace_seconds else signal.SIGKILL


def supervise(command: list[str], directory: Path, *, wall_seconds: float,
              interval: float = .25, grace_seconds: float = 2.0,
              cache_path: Path | None = None, phase_path: Path | None = None,
              solve_seconds: float | None = None, source_state: dict | None = None,
              worker_environment: dict | None = None, hard_stop_immediate: bool = False,
              cooperative_performance_stop: bool = False,
              timebase_guard: bool = False, timebase_policy: str = STRICT,
              stop_on_global_swap: bool = False) -> dict:
    """Supervise one command, with an explicit workflow wall budget."""
    if not command or min(wall_seconds, interval, grace_seconds) <= 0:
        raise ValueError('command and positive monitoring budgets are required')
    if cooperative_performance_stop and (phase_path is None or not hard_stop_immediate or grace_seconds > 60):
        raise ValueError('cooperative stop requires phase registration, immediate hard gates and grace <=60s')
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
    clock_start = clock_sample() if timebase_guard else None
    clock_budget = ClockBudget(clock_start, policy=timebase_policy) if timebase_guard else None
    solve_budget = None
    stop_clock = None
    if timebase_guard:
        summary.update(clock_info=clock_info(), clock_start=clock_start,
                       timebase_policy=timebase_policy, timebase_policy_version=POLICY_VERSION)
    stage = 'launch'
    next_pss_sample = 0.0
    swap_baseline = vmstat_swap_pages()
    try:
        with (directory / 'worker.log').open('w') as output, (directory / 'resources.jsonl').open('w') as timeline:
            environment = os.environ.copy()
            environment.update(worker_environment or {})
            if timebase_guard:
                clock_budget.update(clock_start)
                environment['PHYSICAL_TIMEBASE_GUARD'] = '1'
                environment['PHYSICAL_TIMEBASE_POLICY'] = timebase_policy
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
                sample_options = {}
                if os.environ.get('PHYSICAL_NATIVE_CAPACITY'):
                    sample_options['include_pss'] = time.monotonic() >= next_pss_sample
                    if sample_options['include_pss']:
                        next_pss_sample = time.monotonic() + 5.0
                sample = process_tree_snapshot(os.getpid(), 'workflow', exit_code, **sample_options)
                if os.environ.get('PHYSICAL_NATIVE_CAPACITY'):
                    for member in sample['members']:
                        try:
                            proc = Path('/proc') / str(member['pid'])
                            stat = (proc/'stat').read_text().rsplit(')', 1)[1].split()
                            member['cpu_seconds'] = (int(stat[11])+int(stat[12])) / os.sysconf('SC_CLK_TCK')
                            member['start_ticks'] = int(stat[19])
                            member['affinity'] = sorted(os.sched_getaffinity(member['pid']))
                            member['io'] = {k: int(v) for k, v in
                                            (line.split(':') for line in (proc/'io').read_text().splitlines())}
                        except (OSError, ValueError):
                            member['cost_sample_unavailable'] = True
                current = memory_envelope()
                elapsed = time.monotonic() - started
                phase = json.loads(phase_path.read_text()) if phase_path is not None and phase_path.exists() else {}
                solve_expired = (solve_seconds is not None and phase.get('phase') == 'solve'
                                 and time.monotonic() - phase['phase_started_monotonic'] >= solve_seconds)
                clock_issue = None
                deadline_elapsed = elapsed
                if timebase_guard:
                    clock_now = clock_sample()
                    sample.update(parent_clock=clock_now, parent_clock_start=clock_start)
                    try:
                        sample['workflow_clock_interval'] = clock_budget.update(clock_now)
                        deadline_elapsed = sample['workflow_clock_interval']['budget_seconds']
                        if phase.get('clock_error'):
                            raise TimebaseInconsistency(phase['clock_error'])
                        if phase.get('phase') == 'solve':
                            phase_start = phase.get('phase_started_clock', {})
                            if solve_budget is None or solve_budget.start != phase_start:
                                solve_budget = ClockBudget(phase_start, policy=timebase_policy)
                            sample['solve_clock_interval'] = solve_budget.update(clock_now)
                            solve_expired = (solve_seconds is not None and
                                            sample['solve_clock_interval']['budget_seconds'] >= solve_seconds)
                    except TimebaseInconsistency as exc:
                        clock_issue = str(exc)
                        sample['clock_error'] = clock_issue
                        summary.setdefault('clock_error', clock_issue)
                if not sample['all_status_readable']:
                    reason = 'MONITORING_FAILED'
                else:
                    peak_rss = max(peak_rss, sample['rss_bytes'])
                    peak_swap = max(peak_swap, sample['swap_bytes'])
                    reason = (
                        'RESOURCE_CONTROLLED_STOP' if sample['rss_bytes'] >= cap
                        or current['effective_available_bytes'] < current['reserve_bytes']
                        or sample['swap_bytes'] != 0 else
                        'USER_CONTROLLED_STOP' if timebase_guard and requested_signal else
                        'TIMEBASE_INCONSISTENCY' if clock_issue else
                        'PERFORMANCE_CONTROLLED_STOP' if deadline_elapsed >= wall_seconds or solve_expired else
                        'USER_CONTROLLED_STOP' if requested_signal else None)
                if stop_on_global_swap:
                    current_swap = vmstat_swap_pages()
                    sample['global_swap_pages'] = current_swap
                    swap_reason = global_swap_stop(swap_baseline, current_swap, enabled=True)
                    sample['global_swap_stop_reason'] = swap_reason
                    if swap_reason is not None and reason not in ('RESOURCE_CONTROLLED_STOP', 'MONITORING_FAILED'):
                        reason = swap_reason
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
                    stop_clock = clock_sample() if timebase_guard else None
                    summary['stop_event'] = dict(reason=reason, monotonic=stop_started,
                        timestamp_ns=time.time_ns(), grace_seconds=grace_seconds)
                if classification is not None and children:
                    signum = stop_signal(classification, hard_stop_immediate=hard_stop_immediate,
                        elapsed=budget_elapsed(stop_clock, clock_sample()) if timebase_guard
                        else time.monotonic()-stop_started, grace_seconds=grace_seconds)
                    if (cooperative_performance_stop and classification == 'PERFORMANCE_CONTROLLED_STOP'
                            and signum == signal.SIGTERM):
                        if 'cooperative_stop_request' not in summary:
                            stage = 'cooperative_stop_identity_and_signal'
                            request = _request_cooperative_stop(phase, leader.pid)
                            summary['cooperative_stop_request'] = request
                            summary['first_SIGTERM'] = dict(monotonic=request['monotonic'],
                                timestamp_ns=request['timestamp_ns'], scope='registered application only')
                    else:
                        summary.setdefault('first_'+signal.Signals(signum).name, dict(
                            monotonic=time.monotonic(), timestamp_ns=time.time_ns(), scope='whole child tree'))
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
                if stop_started is not None and (budget_elapsed(stop_clock, clock_sample())
                        if timebase_guard else time.monotonic() - stop_started) > grace_seconds + 10:
                    raise RuntimeError('descendants did not clear after SIGKILL')
                time.sleep(interval)
        summary['cache_metadata_stable'] = True
    except BaseException as exc:
        if stage == 'cooperative_stop_identity_and_signal':
            classification = 'MONITORING_FAILED'
        elif classification is None:
            classification = 'TIMEBASE_INCONSISTENCY' if isinstance(exc, TimebaseInconsistency) else 'MONITORING_FAILED'
        summary.update({'exception_stage': stage, 'exception_type': type(exc).__name__,
                        'exception_message': str(exc), 'cache_metadata_stable': False})
    finally:
        # Also close the tree if sampling, JSON writing, or the parent fails.
        deadline = time.monotonic() + grace_seconds + 10
        cleanup_clock = clock_sample() if timebase_guard else None
        while leader is not None and _children() and (budget_elapsed(cleanup_clock, clock_sample())
                < grace_seconds + 10 if timebase_guard else time.monotonic() < deadline):
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
        if timebase_guard:
            summary['clock_end'] = clock_sample()
            try:
                summary['workflow_clock_interval'] = clock_budget.update(summary['clock_end'])
                if (clock_budget.seconds >= wall_seconds and
                        summary['classification'] == 'COMPLETED'):
                    summary['classification'] = 'PERFORMANCE_CONTROLLED_STOP'
            except TimebaseInconsistency as exc:
                summary['final_clock_error'] = str(exc)
                summary['workflow_clock_interval'] = dict(budget_seconds=clock_budget.seconds,
                                                          budget_complete=False)
                if summary['classification'] in (None, 'COMPLETED'):
                    summary['classification'] = 'TIMEBASE_INCONSISTENCY'
        (directory / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--wall-seconds', type=float, required=True)
    parser.add_argument('--interval', type=float, default=.25)
    parser.add_argument('--grace-seconds', type=float, default=2)
    parser.add_argument('--cache-path', type=Path)
    parser.add_argument('--timebase-guard', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    summary = supervise(command, args.directory, wall_seconds=args.wall_seconds,
                        interval=args.interval, grace_seconds=args.grace_seconds,
                        cache_path=args.cache_path, timebase_guard=args.timebase_guard)
    print(json.dumps(summary, allow_nan=False), flush=True)
    return 0 if summary['classification'] == 'COMPLETED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
