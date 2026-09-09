"""One native-capacity dat per invocation; reuse the existing V5 supervisor."""
import fcntl
import json
import os
import shutil
from pathlib import Path

from src.io.input_loader import InputError


def launch_native_capacity(specification):
    from .task038_launcher import launch_specification
    if os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION') != '1':
        raise InputError('source scripts/activate_myfenics_linux.sh first')
    root = Path(__file__).resolve().parents[2]
    # User-authorized concurrency: only this project's jobs share this lock.
    with (root.parent/'native-capacity-heavy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.sched_setaffinity(0, {8})
        os.environ['OMPI_MCA_hwloc_base_binding_policy'] = 'none'
        os.environ['PHYSICAL_NATIVE_CAPACITY'] = specification.solver['preconditioner']
        memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        if memory['SwapTotal'].strip() != memory['SwapFree'].strip():
            raise InputError('pre-existing global swap usage; no pressure run started')
        filesystem = os.statvfs(root)
        isolation = {'canonical_repository': str(root.parent/'task-repository.git'),
                     'worktree': str(root), 'affinity': sorted(os.sched_getaffinity(0)),
                     'neighbor_concurrent_heavy_authorized': True,
                     'neighbor_files_and_processes_modified': False,
                     'disk_free_bytes': shutil.disk_usage(root).free,
                     'inodes_available': filesystem.f_favail}
        result = launch_specification(specification)
        path = Path(result['run_directory'])/'workstation_isolation.json'
        path.write_text(json.dumps(isolation, indent=2)+'\n')
        return result
