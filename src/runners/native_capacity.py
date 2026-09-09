"""One native-capacity dat per invocation; reuse the existing V5 supervisor."""
import fcntl
import json
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

from benchmarks.task034_wsl_resources import current_cgroup_path, vmstat_swap_pages
from src.io.input_loader import InputError


def _cpu_launch_snapshot(cpus):
    """Record processes last scheduled on the reserved CPUs before launch."""
    snapshot = {str(cpu): [] for cpu in sorted(cpus)}
    own_pid = os.getpid()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            pid = int(proc.name)
            raw = (proc / 'stat').read_text()
            close = raw.rfind(')')
            fields = raw[close + 2:].split()
            processor = int(fields[36])  # /proc/<pid>/stat field 39
            if processor not in cpus:
                continue
            cmdline = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace').strip()
            snapshot[str(processor)].append({
                'pid': pid,
                'self': pid == own_pid,
                'comm': raw[raw.find('(') + 1:close],
                'cmdline': cmdline,
                'affinity': sorted(os.sched_getaffinity(pid)),
            })
        except (OSError, ValueError, IndexError):
            continue
    for rows in snapshot.values():
        rows.sort(key=lambda row: row['pid'])
    return {'captured_by_pid': own_pid, 'cpus': snapshot}


_CGROUP_ROOT = Path('/sys/fs/cgroup')


def _parse_node1_meminfo(text):
    values = {}
    for line in text.splitlines():
        key, separator, value = line.partition(':')
        if separator and key in ('Node 1 MemTotal', 'Node 1 MemFree'):
            fields = value.split()
            if fields and fields[-1] == 'kB':
                values[key] = int(fields[0])
    return values


def _read_swap_snapshot():
    try:
        memory = dict(line.split(':', 1) for line in
                      Path('/proc/meminfo').read_text().splitlines())
    except OSError:
        memory = {}

    def kib_bytes(key):
        try:
            return int(memory[key].split()[0]) * 1024
        except (KeyError, IndexError, ValueError):
            return None

    cgroup = current_cgroup_path()
    cgroup_swap = None
    pid_in_cgroup = None
    cgroup_relative = None
    cgroup_procs_readable = False
    if cgroup is not None:
        try:
            cgroup_relative = cgroup.relative_to(_CGROUP_ROOT).as_posix()
        except ValueError:
            cgroup_relative = None
        try:
            cgroup_swap_value = (cgroup / 'memory.swap.current').read_text().strip()
            cgroup_swap = None if cgroup_swap_value == 'max' else int(cgroup_swap_value)
        except (OSError, ValueError):
            pass
        try:
            members = {int(value) for value in
                       (cgroup / 'cgroup.procs').read_text().split()}
            pid_in_cgroup = os.getpid() in members
            cgroup_procs_readable = True
        except (OSError, ValueError):
            pass
    total = kib_bytes('SwapTotal')
    free = kib_bytes('SwapFree')
    return {
        'swap_total_bytes': total,
        'swap_free_bytes': free,
        'preexisting_global_swap_bytes':
            None if total is None or free is None else max(0, total - free),
        'current_cgroup_path': None if cgroup is None else str(cgroup),
        'current_cgroup_relative': cgroup_relative,
        'current_cgroup_swap_bytes': cgroup_swap,
        'current_pid_in_cgroup': pid_in_cgroup,
        'cgroup_procs_readable': cgroup_procs_readable,
        'global_pswp': vmstat_swap_pages(),
    }


def _launch_swap_snapshot(stability_seconds=1.0):
    first = _read_swap_snapshot()
    time.sleep(stability_seconds)
    second = _read_swap_snapshot()
    first_pswp = first['global_pswp']
    second_pswp = second['global_pswp']
    pswp_delta = {
        key: (None if first_pswp.get(key) is None or second_pswp.get(key) is None
              else second_pswp[key] - first_pswp[key])
        for key in ('pswpin_pages', 'pswpout_pages')
    }
    stable = (
        first['swap_total_bytes'] is not None and
        first['swap_free_bytes'] is not None and
        second['swap_total_bytes'] == first['swap_total_bytes'] and
        second['swap_free_bytes'] == first['swap_free_bytes'] and
        all(value == 0 for value in pswp_delta.values()) and
        first['current_cgroup_path'] is not None and
        first['current_cgroup_path'] == second['current_cgroup_path'] and
        first['current_cgroup_swap_bytes'] is not None and
        second['current_cgroup_swap_bytes'] == first['current_cgroup_swap_bytes']
    )
    return {
        **first,
        'first_read': first,
        'second_read': second,
        'global_pswp_delta': pswp_delta,
        'swap_free_delta_bytes': (
            None if first['swap_free_bytes'] is None or second['swap_free_bytes'] is None
            else second['swap_free_bytes'] - first['swap_free_bytes']),
        'stable_two_read_baseline': stable,
        'stability_interval_seconds': stability_seconds,
    }


def _validate_preexisting_swap(snapshot):
    if not snapshot.get('stable_two_read_baseline'):
        raise InputError('pre-launch swap baseline is unstable or unreadable')
    if snapshot.get('current_cgroup_relative') in (None, '', '.'):
        raise InputError('current task cgroup path is unavailable or root')
    second = snapshot.get('second_read', {})
    if (not snapshot.get('cgroup_procs_readable') or
            not second.get('cgroup_procs_readable') or
            not snapshot.get('current_pid_in_cgroup') or
            not second.get('current_pid_in_cgroup')):
        raise InputError('current task cgroup does not cover the launcher')
    if (snapshot.get('current_cgroup_swap_bytes') is None or
            second.get('current_cgroup_swap_bytes') is None):
        raise InputError('current task cgroup attribution unavailable')
    if snapshot['current_cgroup_relative'] == 'system.slice' and snapshot['current_cgroup_swap_bytes'] != 0:
        raise InputError('system.slice itself has pre-existing swap; no pressure run started')
    if snapshot['current_cgroup_swap_bytes'] != 0:
        raise InputError(
            'pre-existing global swap usage is present in the current task cgroup; '
            'no pressure run started'
        )
    if snapshot.get('global_pswp_delta') != {'pswpin_pages': 0, 'pswpout_pages': 0}:
        raise InputError('global swap activity changed during the pre-launch baseline')
    if snapshot.get('swap_free_delta_bytes') != 0:
        raise InputError('SwapFree changed during the pre-launch baseline')
    if snapshot.get('preexisting_global_swap_bytes') is None:
        raise InputError('global swap baseline is unreadable')
    if snapshot['preexisting_global_swap_bytes'] == 0:
        return 'zero_preexisting_global_swap'
    return 'preexisting_global_swap_reported_outside_current_cgroup'


@contextmanager
def native_capacity_guard(profile, *, memory_policy='none'):
    """Reuse the reviewed native lock, parent CPU, and launch evidence."""
    from src.io.execution_plan import native_memory_policy_prefix
    from src.io.native_capacity_profile import native_profile_facts

    memory_prefix = native_memory_policy_prefix(memory_policy)
    if os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION') != '1':
        raise InputError('source scripts/activate_myfenics_linux.sh first')
    root = Path(__file__).resolve().parents[2]
    with (root.parent/'native-capacity-heavy.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InputError('native-capacity heavy lock is held; no retry started') from exc
        # Keep process-tree sampling off the worker's CPU23.
        os.sched_setaffinity(0, {9})
        os.environ['OMPI_MCA_hwloc_base_binding_policy'] = 'none'
        os.environ['PHYSICAL_NATIVE_CAPACITY'] = profile
        swap_launch = _launch_swap_snapshot()
        swap_launch['policy'] = _validate_preexisting_swap(swap_launch)
        node_admission = None
        if memory_policy == 'membind_node1':
            cgroup = current_cgroup_path()
            allowed_mems = None
            allowed_mems_source = '/proc/self/status:Mems_allowed_list'
            try:
                status = Path('/proc/self/status').read_text()
                raw = next(line.split(':', 1)[1].strip()
                           for line in status.splitlines()
                           if line.startswith('Mems_allowed_list:'))
                allowed_mems = set()
                for item in raw.split(','):
                    bounds = item.split('-', 1)
                    start = int(bounds[0])
                    end = int(bounds[-1])
                    allowed_mems.update(range(start, end + 1))
            except (OSError, IndexError, StopIteration, ValueError):
                allowed_mems = None
            if not allowed_mems or 1 not in allowed_mems:
                raise InputError('native membind_node1 requires Mems_allowed_list including node1')
            node_meminfo = Path('/sys/devices/system/node/node1/meminfo')
            try:
                node_values = _parse_node1_meminfo(node_meminfo.read_text())
            except OSError:
                node_values = {}
            node_total_kib = node_values.get('Node 1 MemTotal')
            node_free_kib = node_values.get('Node 1 MemFree')
            if node_free_kib is None or node_total_kib is None:
                raise InputError('native membind_node1 requires readable node1 MemFree')
            resources = native_profile_facts(profile)['resources']
            from benchmarks.subreaper_watchdog import memory_envelope
            envelope = memory_envelope()
            effective_cap = int(envelope['launch_cap_bytes'])
            if effective_cap <= 0:
                raise InputError('native global memory envelope has no launch capacity')
            node_cap = min(effective_cap, node_free_kib * 1024)
            if node_cap < effective_cap:
                os.environ['PHYSICAL_NATIVE_NODE_CAP_BYTES'] = str(node_cap)
                envelope = memory_envelope()
            if int(envelope['launch_cap_bytes']) > node_free_kib * 1024:
                raise InputError('node1 MemFree cannot support the effective native launch cap')
            node_admission = {
                'policy': 'strict_membind',
                'node': 1,
                'cgroup_path': None if cgroup is None else str(cgroup),
                'allowed_mems': sorted(allowed_mems),
                'allowed_mems_source': allowed_mems_source,
                'node1_memtotal_bytes': node_total_kib * 1024,
                'node1_memfree_bytes': node_free_kib * 1024,
                'node1_memfree_unit': 'bytes_from_kB',
                'effective_launch_cap_before_node1_bytes': effective_cap,
                'effective_launch_cap_bytes': int(envelope['launch_cap_bytes']),
                'node1_cap_tightened': node_cap < effective_cap,
                'global_effective_available_bytes': int(envelope['effective_available_bytes']),
                'global_reserve_bytes': int(envelope['reserve_bytes']),
                'global_reserve_minimum_bytes': int(resources['reserve_min_bytes']),
            }
        filesystem = os.statvfs(root)
        isolation = {'canonical_repository': str(root.parent/'task-repository.git'),
                     'worktree': str(root), 'supervisor_affinity': sorted(os.sched_getaffinity(0)),
                     'worker_affinity': [23],
                     'worker_memory_policy': ({'mode': 'strict_membind', 'node': 1}
                                              if memory_policy == 'membind_node1'
                                              else {'mode': 'default'}),
                     'native_memory_policy': memory_policy,
                     'native_command_prefix': ['/usr/bin/taskset', '-c', '23', *memory_prefix],
                     'node_memory_admission': node_admission,
                     'swap_launch': swap_launch,
                     'native_capacity_profile': profile,
                     'cpu_launch_snapshot': _cpu_launch_snapshot({9, 23}),
                     'neighbor_concurrent_heavy_authorized': True,
                     'neighbor_files_and_processes_modified': False,
                     'disk_free_bytes': shutil.disk_usage(root).free,
                     'inodes_available': filesystem.f_favail}
        yield root, isolation


def launch_native_capacity(specification):
    from .task038_launcher import launch_specification
    memory_policy = specification.execution.get('native_memory_policy', 'none')
    with native_capacity_guard(specification.solver['preconditioner'],
                               memory_policy=memory_policy) as (_root, isolation):
        result = launch_specification(specification, prelaunch_isolation=isolation)
        path = Path(result['run_directory'])/'workstation_isolation.json'
        path.write_text(json.dumps(isolation, indent=2)+'\n')
        return result
