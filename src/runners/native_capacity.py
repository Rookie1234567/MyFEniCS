"""One native-capacity dat per invocation; reuse the existing V5 supervisor."""
import fcntl
import json
import os
import shutil
from pathlib import Path

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


def launch_native_capacity(specification):
    from .task038_launcher import launch_specification
    if os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION') != '1':
        raise InputError('source scripts/activate_myfenics_linux.sh first')
    root = Path(__file__).resolve().parents[2]
    # User-authorized concurrency: only this project's jobs share this lock.
    with (root.parent/'native-capacity-heavy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Keep process-tree sampling off the worker's CPU23.
        os.sched_setaffinity(0, {9})
        os.environ['OMPI_MCA_hwloc_base_binding_policy'] = 'none'
        os.environ['PHYSICAL_NATIVE_CAPACITY'] = specification.solver['preconditioner']
        memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        if memory['SwapTotal'].strip() != memory['SwapFree'].strip():
            raise InputError('pre-existing global swap usage; no pressure run started')
        filesystem = os.statvfs(root)
        isolation = {'canonical_repository': str(root.parent/'task-repository.git'),
                     'worktree': str(root), 'supervisor_affinity': sorted(os.sched_getaffinity(0)),
                     'worker_affinity': [23],
                     'cpu_launch_snapshot': _cpu_launch_snapshot({9, 23}),
                     'neighbor_concurrent_heavy_authorized': True,
                     'neighbor_files_and_processes_modified': False,
                     'disk_free_bytes': shutil.disk_usage(root).free,
                     'inodes_available': filesystem.f_favail}
        result = launch_specification(specification)
        path = Path(result['run_directory'])/'workstation_isolation.json'
        path.write_text(json.dumps(isolation, indent=2)+'\n')
        return result
