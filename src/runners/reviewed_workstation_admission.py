"""Read-only onsite admission for the explicit Review V6 execution profiles."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.io.input_loader import InputError


def _indices(text):
    values = set()
    for item in text.strip().split(','):
        bounds = item.split('-', 1)
        values.update(range(int(bounds[0]), int(bounds[-1])+1))
    return values


def interleaved_admission(resources, worker_cpus):
    from benchmarks.subreaper_watchdog import memory_envelope
    from benchmarks.task034_wsl_resources import current_cgroup_path

    if os.environ.get('TASK39EXTRA_V6_HEAVY_WINDOW') != 'coordinated':
        raise InputError('V6 requires the user-coordinated exclusive heavy window')
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
    allowed_mems = _indices(status['Mems_allowed_list'])
    if not {0, 1}.issubset(allowed_mems):
        raise InputError('V6 interleave requires both nodes in Mems_allowed_list')
    cgroup = current_cgroup_path()
    cpuset_path = cgroup
    allowed_cpus = None
    while cpuset_path is not None and cpuset_path.is_relative_to('/sys/fs/cgroup'):
        effective = cpuset_path/'cpuset.cpus.effective'
        if effective.is_file() and effective.read_text().strip():
            allowed_cpus = _indices(effective.read_text())
            break
        if cpuset_path == Path('/sys/fs/cgroup'):
            break
        cpuset_path = cpuset_path.parent
    if allowed_cpus is None:
        raise InputError('V6 effective cpuset is unavailable in the current cgroup ancestry')
    if not set(worker_cpus).issubset(allowed_cpus):
        raise InputError('V6 worker CPUs are outside the effective cpuset')
    nodes = {}
    cores = set()
    for cpu in worker_cpus:
        topology = Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        core = (int((topology/'physical_package_id').read_text()),
                int((topology/'core_id').read_text()))
        cores.add(core)
    if len(cores) != len(worker_cpus):
        raise InputError('V6 thread CPUs must be distinct physical cores')
    for node in (0, 1):
        path = Path(f'/sys/devices/system/node/node{node}')
        values = {}
        for line in (path/'meminfo').read_text().splitlines():
            key, _, raw = line.partition(':')
            if key.endswith(('MemTotal', 'MemFree')):
                values[key.split()[-1]+'_bytes'] = int(raw.split()[0])*1024
        nodes[str(node)] = dict(values, cpus=(path/'cpulist').read_text().strip())
    envelope = memory_envelope()
    needed = int(resources['rss_hard_limit_bytes'])+int(resources['startup_headroom_bytes'])
    if int(envelope['effective_available_bytes']) < needed:
        raise InputError('V6 startup effective_available is below hard Gate plus headroom')
    large = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            values = dict(line.split(':', 1) for line in (proc/'status').read_text().splitlines())
            rss = int(values.get('VmRSS', '0').split()[0])*1024
            if rss < 10_000_000_000:
                continue
            fields = (proc/'stat').read_text().rsplit(')', 1)[1].split()
            large.append({'pid': int(proc.name), 'start_ticks': int(fields[19]),
                              'comm': values['Name'].strip(), 'rss_bytes': rss,
                              'affinity': sorted(os.sched_getaffinity(int(proc.name)))})
        except (OSError, ValueError, KeyError, IndexError):
            continue
    # A concurrently resident TB-class job cannot share this admitted window.
    # Other visible loads remain recorded and untouched; startup headroom also
    # accounts for their current memory. This is not attribution by command.
    if any(row['rss_bytes'] >= 100_000_000_000 for row in large):
        raise InputError('V6 window has another resident process >=100 GB; no launch')
    probe = subprocess.run(['/usr/bin/numactl', '--interleave=0,1', sys.executable, '-c',
        ("import json,pathlib; a=bytearray(4*1024**2); "
        "maps=pathlib.Path('/proc/self/numa_maps').read_text().splitlines(); "
        "print(json.dumps([r for r in maps if 'interleave' in r]))")],
        capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        raise InputError('V6 interleave qualification failed: '+probe.stderr.strip())
    maps = json.loads(probe.stdout)
    if not maps:
        raise InputError('V6 NUMA probe lacks a read-back interleave policy')
    return {'captured_utc': datetime.now(timezone.utc).isoformat(),
        'policy': 'interleave_nodes0_1', 'nodes': nodes, 'allowed_mems': sorted(allowed_mems),
        'allowed_cpus': sorted(allowed_cpus), 'cpuset_authority_path': str(cpuset_path/'cpuset.cpus.effective'),
        'current_cgroup': str(cgroup), 'worker_cpus': worker_cpus,
        'distinct_physical_cores': len(cores), 'launch_envelope': envelope,
        'effective_available_required_bytes': needed,
        'large_visible_processes': large, 'large_process_scan_threshold_bytes': 10_000_000_000,
        'conflicting_resident_process_threshold_bytes': 100_000_000_000,
        'user_exclusive_window_confirmation': True, 'interleave_probe_maps': maps,
        'neighbors_modified': False}
