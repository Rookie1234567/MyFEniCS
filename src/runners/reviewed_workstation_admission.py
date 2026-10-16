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


def _window_authorization(value, *, parallel_allowed):
    """Interpret the caller's explicit heavy-window authorization honestly."""
    if value == 'coordinated':
        return {
            'window_mode': 'user_coordinated_exclusive',
            'user_exclusive_window_confirmation': True,
            'user_parallel_window_authorization': False,
        }
    if value == 'parallel_authorized' and parallel_allowed:
        return {
            'window_mode': 'user_authorized_cross_project_parallel',
            'user_exclusive_window_confirmation': False,
            'user_parallel_window_authorization': True,
        }
    raise InputError('V6 heavy-window authorization is missing or invalid for this profile')


def _parallel_authorized_profile(profile):
    from src.io.native_capacity_profile import V6_F5_P6_DIRECT_PROFILES

    return profile in V6_F5_P6_DIRECT_PROFILES


def _classify_task40_solver_argv(argv):
    """Classify actual Python entrypoint argv, never Python -c source text."""
    values = [str(value) for value in argv]
    python_index = next((index for index, value in enumerate(values)
                         if Path(value).name.startswith('python')), None)
    if python_index is None:
        return None
    scripts = {
        'run_case.py': 'standard_run_case',
        'task038_input_worker.py': 'task038_input_worker',
        'task038_launcher.py': 'task038_launcher',
        'p6_condensed_direct.py': 'p6_condensed_direct',
    }
    modules = {
        'src.runners.task038_input_worker': 'task038_input_worker',
        'src.runners.task038_launcher': 'task038_launcher',
        'src.runners.p6_condensed_direct': 'p6_condensed_direct',
    }
    index = python_index + 1
    while index < len(values):
        token = values[index]
        if token == '-c':
            return None
        if token == '-m':
            if index + 1 >= len(values):
                return {'kind': 'unknown_task_solver_role', 'entrypoint': 'missing_module'}
            module = values[index + 1]
            role = modules.get(module)
            if role is not None:
                return {'kind': 'task_solver', 'role': role, 'entrypoint': module}
            if module.startswith(('src.runners.task038', 'src.runners.p6_condensed_direct')):
                return {'kind': 'unknown_task_solver_role', 'entrypoint': module}
            return None
        if token in ('-X', '-W', '--check-hash-based-pycs'):
            index += 2
            continue
        basename = Path(token).name
        role = scripts.get(basename)
        if role is not None:
            return {'kind': 'task_solver', 'role': role, 'entrypoint': token}
        if basename.startswith(('task038_', 'p6_condensed_direct')) and basename.endswith('.py'):
            return {'kind': 'unknown_task_solver_role', 'entrypoint': token}
        if token.startswith('-'):
            index += 1
            continue
        return None
    return None


def interleaved_admission(resources, worker_cpus, *, parallel_allowed=False):
    from benchmarks.subreaper_watchdog import memory_envelope
    from benchmarks.task034_wsl_resources import current_cgroup_path

    window = _window_authorization(
        os.environ.get('TASK39EXTRA_V6_HEAVY_WINDOW'),
        parallel_allowed=parallel_allowed,
    )
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
        **window, 'interleave_probe_maps': maps, 'neighbors_modified': False}


def task40_host_floor_interleaved_admission(resources, worker_cpus):
    """Task40 admission: explicit available-memory floor, no legacy RSS cap."""
    import shutil

    from benchmarks.subreaper_watchdog import memory_envelope
    from benchmarks.task034_wsl_resources import current_cgroup_path

    if resources.get('resource_stop_policy') != 'host_available_floor_v1':
        raise InputError('Task40 admission requires host_available_floor_v1')
    if resources.get('rss_hard_limit_bytes') is not None:
        raise InputError('Task40 admission must not inherit an RSS hard cap')
    floor = int(resources.get('minimum_available_bytes') or 0)
    if floor <= 0:
        raise InputError('Task40 admission requires a positive available-memory floor')
    if resources.get('swap_policy') != 'observe_only' or resources.get('stop_on_global_swap') is not False:
        raise InputError('Task40 admission requires observe-only swap policy')

    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
    allowed_mems = _indices(status['Mems_allowed_list'])
    if not {0, 1}.issubset(allowed_mems):
        raise InputError('Task40 interleave requires both nodes in Mems_allowed_list')
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
    if allowed_cpus is None or not set(worker_cpus).issubset(allowed_cpus):
        raise InputError('Task40 worker CPUs are outside or unknown in the effective cpuset')
    cores = set()
    for cpu in worker_cpus:
        topology = Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        cores.add((int((topology/'physical_package_id').read_text()),
                   int((topology/'core_id').read_text())))
    if len(cores) != len(worker_cpus):
        raise InputError('Task40 worker CPUs must be distinct physical cores')

    envelope = memory_envelope()
    available = int(envelope['effective_available_bytes'])
    if available < floor:
        raise InputError(
            f'Task40 effective available memory is below its explicit floor: {available} < {floor}'
        )

    # Refuse a concurrent large solver process without signaling or modifying it.
    ancestors = {os.getpid()}
    current = os.getpid()
    while current > 1:
        try:
            fields = Path(f'/proc/{current}/stat').read_text().rsplit(')', 1)[1].split()
            current = int(fields[1])
        except (OSError, ValueError, IndexError):
            break
        if current > 1:
            ancestors.add(current)
    active_solver_candidates = []
    unknown_solver_role_candidates = []
    large = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            pid = int(proc.name)
            values = dict(line.split(':', 1) for line in (proc/'status').read_text().splitlines())
            rss = int(values.get('VmRSS', '0').split()[0])*1024
            raw_argv = [part.decode('utf-8', 'replace') for part in
                        (proc/'cmdline').read_bytes().split(b'\0') if part]
            if rss >= 10_000_000_000:
                large.append({'pid': pid, 'name': values.get('Name', '').strip(), 'rss_bytes': rss})
            solver_role = _classify_task40_solver_argv(raw_argv)
            if solver_role is not None and pid not in ancestors:
                fields = (proc/'stat').read_text().rsplit(')', 1)[1].split()
                state = fields[0]
                if state not in ('Z', 'X'):
                    candidate = {
                        'pid': pid, 'start_ticks': int(fields[19]),
                        'state': state, 'rss_bytes': rss,
                        'argv': raw_argv[:32], **solver_role,
                    }
                    if solver_role['kind'] == 'task_solver':
                        active_solver_candidates.append(candidate)
                    else:
                        unknown_solver_role_candidates.append(candidate)
        except (OSError, ValueError, KeyError, IndexError):
            continue
    if active_solver_candidates:
        raise InputError(
            'Task40 admission found another active run_case/native solver process: '
            + repr(active_solver_candidates)
        )
    if unknown_solver_role_candidates:
        raise InputError(
            'Task40 admission found an active Task038/P6 Python entrypoint with unknown role: '
            + repr(unknown_solver_role_candidates)
        )
    if any(row['rss_bytes'] >= 100_000_000_000 for row in large):
        raise InputError('Task40 admission found a process >=100 GB; no heavy launch')

    probe = subprocess.run([
        '/usr/bin/numactl', '--interleave=0,1', sys.executable, '-c',
        ("import json,pathlib; a=bytearray(4*1024**2); "
         "maps=pathlib.Path('/proc/self/numa_maps').read_text().splitlines(); "
         "print(json.dumps([r for r in maps if 'interleave' in r]))")
    ], capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        raise InputError('Task40 interleave qualification failed: '+probe.stderr.strip())
    maps = json.loads(probe.stdout)
    if not maps:
        raise InputError('Task40 NUMA probe lacks a read-back interleave policy')
    disk = shutil.disk_usage(Path(__file__).resolve().parents[2])
    return {
        'captured_utc': datetime.now(timezone.utc).isoformat(),
        'policy': 'interleave_nodes0_1',
        'resource_stop_policy': 'host_available_floor_v1',
        'rss_hard_limit_bytes': None,
        'minimum_available_bytes': floor,
        'effective_available_at_admission_bytes': available,
        'nodes': {
            str(node): {
                'meminfo': (Path(f'/sys/devices/system/node/node{node}/meminfo')).read_text().splitlines()[:5],
                'cpus': (Path(f'/sys/devices/system/node/node{node}/cpulist')).read_text().strip(),
            }
            for node in (0, 1)
        },
        'allowed_mems': sorted(allowed_mems),
        'allowed_cpus': sorted(allowed_cpus),
        'cpuset_authority_path': str(cpuset_path/'cpuset.cpus.effective'),
        'current_cgroup': str(cgroup),
        'worker_cpus': list(worker_cpus),
        'distinct_physical_cores': len(cores),
        'large_visible_processes': large,
        'active_solver_candidates': active_solver_candidates,
        'unknown_solver_role_candidates': unknown_solver_role_candidates,
        'interleave_probe_maps': maps,
        'worktree_disk_free_bytes_at_admission': disk.free,
        'neighbors_modified': False,
        'legacy_launch_cap_used_for_admission': False,
    }
