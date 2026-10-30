"""Bounded single-process-group supervisor for explicit cloud experiments.

This module observes processes and resources only; it contains no numerical
method. It neither raises limits nor retries a failed child.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time


def proc_facts(pid: int) -> dict:
    path = Path('/proc') / str(pid)
    stat = (path / 'stat').read_text()
    parts = stat[stat.rfind(')') + 2:].split()
    status = (path / 'status').read_text()
    memory = {}
    for line in status.splitlines():
        if line.startswith(('VmRSS:', 'VmSwap:')):
            key, value, *_ = line.split()
            memory[key.rstrip(':')] = int(value) * 1024
    return dict(pid=pid, ppid=int(parts[1]), pgrp=int(parts[2]),
                start_ticks=int(parts[19]), cpu_ticks=int(parts[11])+int(parts[12]), rss=memory.get('VmRSS', 0),
                swap=memory.get('VmSwap', 0), state=parts[0])


def group_facts(pgrp: int, tracked: dict[int, int]) -> tuple[list[dict], list[int]]:
    all_facts, errors = {}, []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        pid = int(entry.name)
        try:
            all_facts[pid] = proc_facts(pid)
        except FileNotFoundError:
            continue
        except (PermissionError, OSError, ValueError):
            if pid in tracked:
                errors.append(pid)
    members = {p for p, f in all_facts.items() if f['pgrp'] == pgrp}
    members.update(p for p, start in tracked.items()
                   if p in all_facts and all_facts[p]['start_ticks'] == start)
    changed = True
    while changed:
        extra = {p for p, f in all_facts.items() if f['ppid'] in members} - members
        changed = bool(extra)
        members.update(extra)
    tracked.update({p: all_facts[p]['start_ticks'] for p in members})
    return [all_facts[p] for p in sorted(members)], errors


def cleanup_child(proc, tracked) -> tuple[int | None, list, list]:
    """Always signal the owned group, then verified escaped descendants."""
    errors = []
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass
        except OSError as exc:
            errors.append(repr(exc))
        for pid, start in list(tracked.items()):
            try:
                if proc_facts(pid)['start_ticks'] == start:
                    os.kill(pid, sig)
            except FileNotFoundError:
                pass
            except ProcessLookupError:
                pass
            except (OSError, ValueError, KeyError) as exc:
                errors.append(repr(exc))
        time.sleep(0.5)
    try:
        code = proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        code = None
        errors.append('child_wait_timeout_after_sigkill')
    try:
        remaining, read_errors = group_facts(proc.pid, tracked)
        errors.extend(read_errors)
        remaining = [x for x in remaining if x['state'] != 'Z']
    except (OSError, ValueError, KeyError) as exc:
        remaining = [{'unknown': True}]
        errors.append(repr(exc))
    return code, remaining, errors


def system_facts(directory: Path) -> dict:
    mem = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value, *_ = line.split()
        mem[key.rstrip(':')] = int(value) * 1024
    vm = dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines())
    return dict(available=mem['MemAvailable'], total=mem['MemTotal'],
                swap_used=mem['SwapTotal'] - mem['SwapFree'],
                pswpin=int(vm['pswpin']), pswpout=int(vm['pswpout']),
                disk_free=shutil.disk_usage(directory).free)


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def regular_artifact_bytes(directory):
    """Count run-owned bytes only; cache symlinks borrow already-existing files."""
    total = 0
    for path in Path(directory).rglob('*'):
        if path.is_symlink():
            continue
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            continue
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seconds', required=True, type=float)
    parser.add_argument('--rss-bytes', required=True, type=int)
    parser.add_argument('--available-bytes', type=int, default=1 << 30)
    parser.add_argument('--disk-free-bytes', type=int, default=4 << 30)
    parser.add_argument('--new-artifact-cap-bytes', type=int)
    parser.add_argument('--interval', type=float, default=0.5)
    parser.add_argument('--ledger-batch')
    parser.add_argument('--source-sha')
    parser.add_argument('--ledger-stage', default='Q4_ORIGINAL')
    parser.add_argument('--internal-time-policy', choices=('enforce', 'observe_only'), default='enforce')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command or min(args.seconds, args.rss_bytes, args.interval) <= 0:
        parser.error('A command and positive time, RSS, interval are required')
    if args.ledger_batch and not args.source_sha:
        parser.error('--ledger-batch requires --source-sha')
    if args.new_artifact_cap_bytes is not None and args.new_artifact_cap_bytes <= 0:
        parser.error('positive optional new-artifact cap required')
    args.output.mkdir(parents=True, exist_ok=False)
    baseline = system_facts(args.output)
    limits = dict(seconds=args.seconds, rss_bytes=args.rss_bytes,
                  available_bytes=args.available_bytes,
                  disk_free_bytes=args.disk_free_bytes, zero_swap=True)
    admission = (baseline['available'] >= args.available_bytes and
                 baseline['disk_free'] >= args.disk_free_bytes and
                 baseline['swap_used'] == 0)
    if args.new_artifact_cap_bytes is not None:
        limits['new_artifact_cap_bytes'] = args.new_artifact_cap_bytes
        admission &= baseline['disk_free'] >= args.disk_free_bytes + args.new_artifact_cap_bytes
    summary = dict(schema='cloud-numeric-supervisor.v1', command=command,
                   baseline=baseline, limits=limits, status='ADMISSION_FAILED',
                   numerical_result_authority=False)
    if not admission:
        atomic_json(args.output / 'summary.json', summary)
        return 3
    env = dict(os.environ)
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
        env[name] = '1'
    env['PHYSICAL_WATCHDOG_PARENT_PID'] = str(os.getpid())
    env['PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES'] = str(args.rss_bytes)
    env['PHYSICAL_WATCHDOG_PHASE_PATH'] = str((args.output / 'workflow_phase.json').resolve())
    started = time.monotonic()
    ledger = None
    if args.ledger_batch:
        clock_start = dict(monotonic=started,
                           boottime=time.clock_gettime(time.CLOCK_BOOTTIME),
                           utc_ns=time.time_ns())
        attempt = dict(source_sha=args.source_sha, status='RUNNING',
                       reserved_seconds=args.seconds, time_policy=args.internal_time_policy,
                       workflow_clock_start=clock_start)
        ledger = dict(schema='cloud-numeric-ledger.v1', batch_identity=args.ledger_batch,
                      total_budget_seconds=args.seconds, elapsed_seconds=0.0,
                      policy_debits=[], fresh_worker_count=1,
                      unique_bug_replay_count=0,
                      external_time_policy='enforce',
                      internal_time_policy=args.internal_time_policy,
                      stages={args.ledger_stage: {'attempts': [attempt], 'active_attempt': 0}})
        ledger_path = (args.output / 'shared_workflow_ledger.json').resolve()
        atomic_json(ledger_path, ledger)
        env['PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH'] = str(ledger_path)
        env['PHYSICAL_WATCHDOG_SHARED_ATTEMPT_INDEX'] = '0'
    tracked: dict[int, int] = {}
    peak = 0
    samples = 0
    reason = None
    interrupt_requested = []

    def request_stop(signum, _frame):
        interrupt_requested.append(int(signum))

    old_handlers = {sig: signal.signal(sig, request_stop)
                    for sig in (signal.SIGINT, signal.SIGTERM)}
    with (args.output / 'stdout.log').open('wb') as out, \
         (args.output / 'stderr.log').open('wb') as err, \
         (args.output / 'resources.jsonl').open('w') as log:
        proc = subprocess.Popen(command, stdout=out, stderr=err, env=env,
                                start_new_session=True)
        try:
            tracked[proc.pid] = proc_facts(proc.pid)['start_ticks']
            while True:
                elapsed = time.monotonic() - started
                members, errors = group_facts(proc.pid, tracked)
                system = system_facts(args.output)
                supervisor = proc_facts(os.getpid())
                rss = sum(x['rss'] for x in members) + supervisor['rss']
                peak = max(peak, rss)
                sample = dict(elapsed=elapsed, process_tree=members,
                              supervisor=supervisor, rss=rss,
                              unreadable=errors, system=system)
                if args.new_artifact_cap_bytes is not None:
                    sample['new_regular_artifact_bytes'] = regular_artifact_bytes(args.output)
                log.write(json.dumps(sample, sort_keys=True) + '\n')
                log.flush()
                samples += 1
                if interrupt_requested:
                    reason = 'REQUESTED_STOP'
                elif elapsed > args.seconds:
                    reason = 'TIME_LIMIT'
                elif errors:
                    reason = 'RESOURCE_OBSERVATION_FAILED'
                elif rss > args.rss_bytes:
                    reason = 'PROCESS_TREE_RSS_LIMIT'
                elif system['available'] < args.available_bytes:
                    reason = 'HOST_AVAILABLE_MEMORY_LIMIT'
                elif system['disk_free'] < args.disk_free_bytes:
                    reason = 'DISK_HEADROOM_LIMIT'
                elif (args.new_artifact_cap_bytes is not None and
                      sample['new_regular_artifact_bytes'] >= args.new_artifact_cap_bytes):
                    reason = 'NEW_ARTIFACT_LIMIT'
                elif (sum(x['swap'] for x in members) or supervisor['swap'] or system['swap_used'] or
                      system['pswpin'] != baseline['pswpin'] or
                      system['pswpout'] != baseline['pswpout']):
                    reason = 'SWAP_ACTIVITY_OBSERVED_ATTRIBUTION_NOT_ASSUMED'
                if reason or proc.poll() is not None:
                    break
                time.sleep(args.interval)
        except BaseException as exc:
            reason = 'SUPERVISOR_OBSERVATION_OR_LOG_FAILURE'
            summary['supervisor_error'] = repr(exc)
        finally:
            code, remaining, errors = cleanup_child(proc, tracked)
    for sig, handler in old_handlers.items():
        signal.signal(sig, handler)
    summary.update(status=('CONTROLLED_STOP' if reason else
                           'CHILD_EXIT_ZERO' if code == 0 else 'CHILD_FAILED'),
                   stop_reason=reason, child_exit_code=code,
                   elapsed_seconds=time.monotonic() - started,
                   process_tree_peak_rss_bytes=peak if samples else None,
                   resource_sample_count=samples, remaining=remaining,
                   cleanup_verified=not remaining and not errors)
    if ledger is not None:
        stage_record = ledger['stages'][args.ledger_stage]
        stage_record['active_attempt'] = None
        stage_record['attempts'][0].update(
            status=summary['status'], elapsed_seconds=summary['elapsed_seconds'],
            stop_reason=reason, child_exit_code=code)
        ledger['elapsed_seconds'] = summary['elapsed_seconds']
        atomic_json(ledger_path, ledger)
    atomic_json(args.output / 'summary.json', summary)
    return 0 if code == 0 and not reason and not remaining and not errors else 4


if __name__ == '__main__':
    raise SystemExit(main())
