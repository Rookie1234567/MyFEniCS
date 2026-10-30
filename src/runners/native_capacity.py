"""One native-capacity dat per invocation; reuse the existing V5 supervisor."""
import fcntl
import json
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from benchmarks.task034_wsl_resources import current_cgroup_path, vmstat_swap_pages
from src.io.input_loader import InputError


def _native_capacity_host_lock(root: Path, profile: str) -> tuple[Path, Path]:
    """Choose the shared host lock for Task40, preserving every older path."""
    from src.io.native_capacity_profile import TASK40_PHI90_P6_DIRECT_PROFILES

    if profile not in TASK40_PHI90_P6_DIRECT_PROFILES:
        return root.parent/'native-capacity-heavy.lock', root.parent/'task-repository.git'
    try:
        completed = subprocess.run(
            ['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
            cwd=root, capture_output=True, text=True, check=True,
        )
        common = Path(completed.stdout.strip())
        if not common.is_absolute():
            common = (root/common).resolve()
        common = common.resolve(strict=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InputError(f'Task40 cannot identify canonical shared git directory: {exc}') from exc
    if common.name != 'task-repository.git' or not common.is_dir():
        raise InputError(
            f'Task40 canonical shared git directory is unexpected: {common}'
        )
    # Older Maxwell3D-Lab worktrees place the lock beside this common bare repo.
    return common.parent/'native-capacity-heavy.lock', common


@contextmanager
def _native_capacity_launch_lock(root, profile, task_run_id):
    """Keep legacy launches exclusive; share only the reviewed exact pair."""
    from src.runners.task40_exact_parallel_pair import (
        CANONICAL_COMMON_REPOSITORY,
        CANONICAL_HEAVY_LOCK_PATH,
        PAIR_SCOPE_PATH_ENV,
        PAIR_SCOPE_SHA_ENV,
        acquire_pair_runtime_locks,
        load_pair_scope,
        pair_role_if_member,
    )

    scope_path = os.environ.get(PAIR_SCOPE_PATH_ENV)
    scope_sha = os.environ.get(PAIR_SCOPE_SHA_ENV)
    role = pair_role_if_member(profile, task_run_id or "")
    if role is None:
        if scope_path is not None or scope_sha is not None:
            raise InputError(
                'Task40 exact-pair scope cannot authorize a non-member profile/run identity'
            )
        # Leave ordinary Task40 and every legacy profile on its existing
        # worktree/common-dir lock resolver.
        lock_path, common_repository = _native_capacity_host_lock(root, profile)
        with lock_path.open('a') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise InputError('native-capacity heavy lock is held; no retry started') from exc
            yield stream, lock_path, common_repository, None
        return

    if scope_path is None or scope_sha is None:
        raise InputError('Task40 exact-pair member requires its reviewed scope path and SHA256')
    scope = load_pair_scope(scope_path=scope_path, expected_sha256=scope_sha)
    lock_contract = scope.get('canonical_host_lock', {})
    lock_path = Path(lock_contract.get('path', ''))
    if (
        not lock_path.is_absolute()
        or lock_path.resolve() != CANONICAL_HEAVY_LOCK_PATH.resolve()
        or lock_contract.get('canonical_lock_must_preexist') is not True
        or lock_contract.get('keep_canonical_lock') is not True
        or not lock_path.is_file()
    ):
        raise InputError('Task40 exact-pair scope names a different canonical heavy lock')
    try:
        common_repository = CANONICAL_COMMON_REPOSITORY.resolve(strict=True)
        common_check = subprocess.run(
            [
                'git', '--git-dir', str(common_repository),
                'rev-parse', '--is-bare-repository',
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InputError(
            f'Task40 exact-pair canonical repository is unavailable: {exc}'
        ) from exc
    if (
        common_repository.name != 'task-repository.git'
        or not common_repository.is_dir()
        or common_check.stdout.strip() != 'true'
    ):
        raise InputError(
            f'Task40 exact-pair canonical repository is unexpected: {common_repository}'
        )
    with acquire_pair_runtime_locks(
        role=role, canonical_lock_path=lock_path
    ) as pair_locks:
        yield pair_locks, lock_path, common_repository, {
            'role': role,
            'scope_path': str(Path(scope_path).resolve()),
            'scope_sha256': str(scope_sha).lower(),
            'scope': scope,
        }


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


def _validate_preexisting_swap(snapshot, *, observe_only=False):
    # Review V3's new profile records the same two-read baseline but does not
    # turn job/global swap activity into a launch veto.  Legacy profiles keep
    # the fail-closed checks below unchanged.
    if observe_only:
        if snapshot.get('stable_two_read_baseline'):
            if snapshot.get('preexisting_global_swap_bytes') == 0:
                return 'observe_only_zero_preexisting_global_swap'
            return 'observe_only_preexisting_global_swap_reported'
        return 'observe_only_baseline_unavailable'
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
def native_capacity_guard(profile, *, memory_policy='none', task_run_id=None):
    """Reuse the reviewed native lock, parent CPU, and launch evidence."""
    from src.io.execution_plan import native_memory_policy_prefix
    from src.io.native_capacity_profile import (
        TASK40_PHI90_P6_DIRECT_PROFILES,
        native_profile_facts,
    )

    memory_prefix = native_memory_policy_prefix(memory_policy)
    if os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION') != '1':
        raise InputError('source scripts/activate_myfenics_linux.sh first')
    root = Path(__file__).resolve().parents[2]
    profile_facts = native_profile_facts(profile)
    supervisor_cpu = int(profile_facts.get('native_execution', {}).get('supervisor_cpu', 9))
    worker_cpu = profile_facts.get('native_execution', {}).get('worker_cpu', 23)
    worker_cpus = profile_facts.get('native_execution', {}).get('worker_cpus', [worker_cpu])
    with _native_capacity_launch_lock(root, profile, task_run_id) as (
        _lock, lock_path, common_repository, pair_context
    ):
        if pair_context is not None and (
            memory_policy != 'interleave_nodes0_1'
            or profile_facts['resources'].get('resource_stop_policy')
            != 'host_available_floor_v1'
        ):
            raise InputError(
                'Task40 exact-pair members require the reviewed host-floor/interleave admission path'
            )
        # Keep process-tree sampling on the reviewed profile supervisor CPU.
        os.sched_setaffinity(0, {supervisor_cpu})
        os.environ['OMPI_MCA_hwloc_base_binding_policy'] = 'none'
        os.environ['PHYSICAL_NATIVE_CAPACITY'] = profile
        observe_only_swap = profile_facts['resources'].get('swap_policy') == 'observe_only'
        swap_launch = _launch_swap_snapshot()
        swap_launch['policy'] = _validate_preexisting_swap(
            swap_launch, observe_only=observe_only_swap
        )
        node_admission = None
        if memory_policy == 'interleave_nodes0_1':
            os.environ.pop('PHYSICAL_NATIVE_NODE_CAP_BYTES', None)
            if profile_facts['resources'].get('resource_stop_policy') == 'host_available_floor_v1':
                from .reviewed_workstation_admission import (
                    _TASK40_PARALLEL_AUTH_FILE_ENV,
                    _TASK40_PARALLEL_AUTH_SHA_ENV,
                    task40_host_floor_interleaved_admission,
                )
                node_admission = task40_host_floor_interleaved_admission(
                    profile_facts['resources'], worker_cpus,
                    task_profile=profile,
                    task_run_id=task_run_id,
                    parallel_authority_path=os.environ.get(_TASK40_PARALLEL_AUTH_FILE_ENV),
                    parallel_authority_sha256=os.environ.get(_TASK40_PARALLEL_AUTH_SHA_ENV),
                    pair_scope_path=(None if pair_context is None else pair_context['scope_path']),
                    pair_scope_sha256=(None if pair_context is None else pair_context['scope_sha256']),
                    pair_role=(None if pair_context is None else pair_context['role']),
                    current_service_unit=os.environ.get('TASK40_EXACT_PARALLEL_PAIR_SERVICE_UNIT'),
                    supervisor_cpu=supervisor_cpu,
                )
            else:
                from .reviewed_workstation_admission import (
                    _parallel_authorized_profile,
                    interleaved_admission,
                )
                node_admission = interleaved_admission(
                    profile_facts['resources'], worker_cpus,
                    parallel_allowed=_parallel_authorized_profile(profile),
                )
        if memory_policy in {'membind_node1', 'preferred_node1'}:
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
                raise InputError('native node1 memory policy requires Mems_allowed_list including node1')
            node_meminfo = Path('/sys/devices/system/node/node1/meminfo')
            try:
                node_values = _parse_node1_meminfo(node_meminfo.read_text())
            except OSError:
                node_values = {}
            node_total_kib = node_values.get('Node 1 MemTotal')
            node_free_kib = node_values.get('Node 1 MemFree')
            if node_free_kib is None or node_total_kib is None:
                raise InputError('native node1 memory policy requires readable node1 MemFree')
            resources = native_profile_facts(profile)['resources']
            from benchmarks.subreaper_watchdog import memory_envelope
            if memory_policy == 'preferred_node1':
                # Do not inherit a cap tightened by an earlier strict-node1 launch.
                os.environ.pop('PHYSICAL_NATIVE_NODE_CAP_BYTES', None)
            envelope = memory_envelope()
            effective_cap = int(envelope['launch_cap_bytes'])
            if effective_cap <= 0:
                raise InputError('native global memory envelope has no launch capacity')
            node_cap = effective_cap
            if memory_policy == 'membind_node1':
                node_cap = min(effective_cap, node_free_kib * 1024)
            if memory_policy == 'membind_node1' and node_cap < effective_cap:
                os.environ['PHYSICAL_NATIVE_NODE_CAP_BYTES'] = str(node_cap)
                envelope = memory_envelope()
            if (memory_policy == 'membind_node1' and
                    int(envelope['launch_cap_bytes']) > node_free_kib * 1024):
                raise InputError('node1 MemFree cannot support the effective native launch cap')
            node_admission = {
                'policy': ('strict_membind' if memory_policy == 'membind_node1'
                           else 'preferred_node1'),
                'node': 1,
                'fallback_allowed': memory_policy == 'preferred_node1',
                'cgroup_path': None if cgroup is None else str(cgroup),
                'allowed_mems': sorted(allowed_mems),
                'allowed_mems_source': allowed_mems_source,
                'node1_memtotal_bytes': node_total_kib * 1024,
                'node1_memfree_bytes': node_free_kib * 1024,
                'node1_memfree_unit': 'bytes_from_kB',
                'effective_launch_cap_before_node1_bytes': effective_cap,
                'effective_launch_cap_bytes': int(envelope['launch_cap_bytes']),
                'node1_cap_tightened': node_cap < effective_cap,
                'node1_memfree_below_effective_cap': node_free_kib * 1024 < effective_cap,
                'global_effective_available_bytes': int(envelope['effective_available_bytes']),
                'global_reserve_bytes': int(envelope['reserve_bytes']),
                'global_reserve_minimum_bytes': int(resources['reserve_min_bytes']),
            }
        filesystem = os.statvfs(root)
        isolation = {'canonical_repository': str(common_repository),
                     'native_capacity_heavy_lock': str(lock_path.resolve()),
                     'native_capacity_lock_scope': (
                         'canonical_host_shared_with_exact_task40_pair'
                         if pair_context is not None else
                         'canonical_host_shared_with_task39_worktrees'
                         if profile in TASK40_PHI90_P6_DIRECT_PROFILES else
                         'legacy_worktree_parent_unchanged'
                     ),
                     'worktree': str(root), 'supervisor_affinity': sorted(os.sched_getaffinity(0)),
                     'supervisor_cpu': supervisor_cpu,
                     'worker_affinity': worker_cpus,
                     'worker_memory_policy': ({'mode': 'strict_membind', 'node': 1}
                                              if memory_policy == 'membind_node1'
                                              else {'mode': 'preferred', 'preferred_node': 1,
                                                    'fallback': 'allowed_mems'}
                                              if memory_policy == 'preferred_node1'
                                              else {'mode': 'interleave', 'nodes': [0, 1]}
                                              if memory_policy == 'interleave_nodes0_1'
                                              else {'mode': 'default'}),
                     'native_memory_policy': memory_policy,
                     'native_command_prefix': ['/usr/bin/taskset', '-c', ','.join(map(str, worker_cpus)), *memory_prefix],
                     'node_memory_admission': node_admission,
                     'swap_launch': swap_launch,
                     'native_capacity_profile': profile,
                     'cpu_launch_snapshot': _cpu_launch_snapshot({supervisor_cpu, *worker_cpus}),
                     'exact_parallel_pair': (None if pair_context is None else {
                         'pair_id': pair_context['scope']['pair_id'],
                         'role': pair_context['role'],
                         'scope_path': pair_context['scope_path'],
                         'scope_sha256': pair_context['scope_sha256'],
                         'canonical_lock_mode': 'shared_nonblocking',
                         'pair_membership_lock_mode': 'shared_nonblocking',
                         'member_role_lock_mode': 'exclusive_nonblocking',
                     }),
                     'profile_concurrent_neighbor_authorized': profile_facts['resources']['concurrent_neighbor_authorized'],
                     'neighbor_concurrent_heavy_authorized': (
                         profile_facts['resources']['concurrent_neighbor_authorized']
                         or bool(node_admission and node_admission.get(
                             'user_parallel_window_authorization'
                         ))
                     ),
                     'neighbor_files_and_processes_modified': False,
                     'disk_free_bytes': shutil.disk_usage(root).free,
                     'inodes_available': filesystem.f_favail}
        env_names = (
            'PHYSICAL_WATCHDOG_PSS_POLICY',
            'OMP_NUM_THREADS',
            'OPENBLAS_NUM_THREADS',
            'MKL_NUM_THREADS',
            'BLIS_NUM_THREADS',
            'NUMEXPR_NUM_THREADS',
        )
        previous_environment = {name: os.environ.get(name) for name in env_names}
        if profile_facts['resources'].get('pss_sampling_policy') == 'disabled_by_profile':
            os.environ['PHYSICAL_WATCHDOG_PSS_POLICY'] = 'disabled_by_profile'
            threads = str(profile_facts['native_execution']['math_threads'])
            for name in (
                'OMP_NUM_THREADS',
                'OPENBLAS_NUM_THREADS',
                'MKL_NUM_THREADS',
                'BLIS_NUM_THREADS',
                'NUMEXPR_NUM_THREADS',
            ):
                os.environ[name] = threads
        try:
            yield root, isolation
        finally:
            for name, value in previous_environment.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value



def launch_native_capacity(specification, *, setup_only: bool = False):
    from src.io.native_capacity_profile import native_capacity_profile_identity

    from .task038_launcher import launch_specification

    memory_policy = specification.execution.get('native_memory_policy', 'none')
    profile = native_capacity_profile_identity(
        specification.method.get('kind'), specification.solver
    )
    if profile is None:
        raise InputError('native capacity launch requires an explicit native profile')
    with native_capacity_guard(
        profile,
        memory_policy=memory_policy,
        task_run_id=specification.identity.get('run_id'),
    ) as (_root, isolation):
        launch_kwargs = {'prelaunch_isolation': isolation}
        if setup_only:
            launch_kwargs['setup_only'] = True
        result = launch_specification(specification, **launch_kwargs)
        path = Path(result['run_directory'])/'workstation_isolation.json'
        path.write_text(json.dumps(isolation, indent=2)+'\n')
        return result
