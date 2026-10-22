"""Read-only onsite admission for the explicit Review V6 execution profiles."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src.io.input_loader import InputError

_TASK40_PARALLEL_AUTH_FILE_ENV = 'TASK40_PARALLEL_AUTHORIZATION_FILE'
_TASK40_PARALLEL_AUTH_SHA_ENV = 'TASK40_PARALLEL_AUTHORIZATION_SHA256'
_TASK40_PARALLEL_NEIGHBOR_RUN_ID = 'task41extra_b0_p6_phi90_07nm_iterative'
_TASK40_PARALLEL_LEGACY_SCOPE = frozenset({
    (
        'task40para_phi90_13p5_D15_Z3_3_p6_direct_v1',
        'task40_phi90_13p5_D15_Z3_3_p6_direct_v1',
    ),
    (
        'task40para_phi90_13p5_D15_X2_p6_direct_v1',
        'task40_phi90_13p5_D15_X2_p6_direct_v1',
    ),
})
_TASK40_PARALLEL_ALLOWED_RUNS = _TASK40_PARALLEL_LEGACY_SCOPE | frozenset(
    (
        f'task40para_phi90_13p5_D15_Y3_K{k}_p6_direct_v1',
        f'task40_phi90_13p5_D15_Y3_K{k}_p6_direct_v1',
    )
    for k in range(1, 5)
)


def _proc_root():
    return Path('/proc')


def _sys_root():
    return Path('/sys')


def _sleep_for_cpu_sample(seconds):
    time.sleep(seconds)


def _interleave_probe():
    return subprocess.run([
        '/usr/bin/numactl', '--interleave=0,1', sys.executable, '-c',
        ("import json,pathlib; a=bytearray(4*1024**2); "
         "maps=pathlib.Path('/proc/self/numa_maps').read_text().splitlines(); "
         "print(json.dumps([r for r in maps if 'interleave' in r]))")
    ], capture_output=True, text=True, check=False)


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


def _read_proc_identity(proc_root, pid):
    process = Path(proc_root) / str(int(pid))
    raw_stat = (process / 'stat').read_text()
    fields = raw_stat.rsplit(')', 1)[1].split()
    status = dict(
        line.split(':', 1)
        for line in (process / 'status').read_text().splitlines()
        if ':' in line
    )
    argv = [
        part.decode('utf-8', 'replace')
        for part in (process / 'cmdline').read_bytes().split(b'\0')
        if part
    ]
    return {
        'pid': int(pid),
        'state': fields[0],
        'ppid': int(fields[1]),
        'start_ticks': int(fields[19]),
        'utime_ticks': int(fields[11]),
        'stime_ticks': int(fields[12]),
        'cwd': str((process / 'cwd').resolve()),
        'argv': argv,
        'rss_bytes': int(status.get('VmRSS', '0').split()[0]) * 1024,
    }


def _task40_parallel_authorization(path, expected_sha256, profile, run_id):
    if not path or not expected_sha256:
        raise InputError('Task40 parallel authorization path and SHA256 must be supplied together')
    try:
        raw = Path(path).read_bytes()
        actual_sha = hashlib.sha256(raw).hexdigest()
        record = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f'Task40 parallel authorization record is unreadable: {exc}') from exc
    if actual_sha != str(expected_sha256).lower():
        raise InputError('Task40 parallel authorization record SHA256 mismatch')
    if record.get('schema') != 'task40.cross_project_parallel_authority.v1':
        raise InputError('Task40 parallel authorization schema is unsupported')
    authorized_runs = frozenset({
        (item.get('profile_identity'), item.get('run_id'))
        for item in record.get('scope', {}).get('task40_runs', [])
        if isinstance(item, dict)
    })
    requested_run = (str(profile), str(run_id))
    if requested_run not in _TASK40_PARALLEL_ALLOWED_RUNS:
        raise InputError('Task40 parallel authorization does not cover a reviewed run identity')
    if authorized_runs not in (
        _TASK40_PARALLEL_LEGACY_SCOPE,
        frozenset({requested_run}),
    ):
        raise InputError('Task40 parallel authorization must bind one exact run or the legacy pair')
    if requested_run not in authorized_runs:
        raise InputError('Task40 parallel authorization does not cover this profile/run_id')
    neighbor = record.get('task41_neighbor')
    if not isinstance(neighbor, dict) or neighbor.get('run_id') != _TASK40_PARALLEL_NEIGHBOR_RUN_ID:
        raise InputError('Task40 parallel authorization does not identify the reviewed Task41 run')
    parent_path = record.get('parent_user_authority_path')
    parent_sha = record.get('parent_user_authority_sha256')
    if not parent_path or not parent_sha:
        raise InputError('Task40 parallel authorization lacks its parent user-authority binding')
    try:
        parent_raw = Path(parent_path).read_bytes()
        parent_actual_sha = hashlib.sha256(parent_raw).hexdigest()
        parent_record = json.loads(parent_raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f'Task40 parent user-authority record is unreadable: {exc}') from exc
    if parent_actual_sha != str(parent_sha).lower():
        raise InputError('Task40 parent user-authority SHA256 mismatch')
    if parent_record.get('schema') != 'task40.user_parallel_authority.v1':
        raise InputError('Task40 parent user-authority schema is unsupported')
    if parent_record.get('scope', {}).get('task') != 'Task40':
        raise InputError('Task40 parent authority belongs to a different task')
    bound_roles = {
        node.get('role'): (int(node.get('pid', -1)), int(node.get('start_ticks', -1)))
        for node in neighbor.get('processes', []) if isinstance(node, dict)
    }
    parent_roles = {
        'root': 'root', 'MPI': 'mpi', 'worker': 'worker',
    }
    parent_identities = {
        row.get('role'): (int(row.get('pid', -1)), int(row.get('start_ticks', -1)))
        for row in parent_record.get('authorized_neighbor_identity', [])
        if isinstance(row, dict)
    }
    if any(
        parent_identities.get(parent_role) != bound_roles.get(process_role)
        for parent_role, process_role in parent_roles.items()
    ):
        raise InputError('Task40 process identities differ from the parent user-authority record')
    cpu_path = record.get('cpu_activity_sample_path')
    cpu_sha = record.get('cpu_activity_sample_sha256')
    if not cpu_path or not cpu_sha:
        raise InputError('Task40 parallel authorization lacks its bounded CPU-sample binding')
    try:
        cpu_raw = Path(cpu_path).read_bytes()
        cpu_actual_sha = hashlib.sha256(cpu_raw).hexdigest()
        cpu_record = json.loads(cpu_raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f'Task40 CPU-sample record is unreadable: {exc}') from exc
    if cpu_actual_sha != str(cpu_sha).lower():
        raise InputError('Task40 CPU-sample SHA256 mismatch')
    if cpu_record.get('exclusive_cpu_claim') is not False:
        raise InputError('Task40 CPU sample must not claim exclusive CPU ownership')
    if float(cpu_record.get('sample_seconds', 0.0)) < 1.0:
        raise InputError('Task40 CPU activity sample is shorter than the bounded minimum')
    sample_threads = cpu_record.get('neighbor_threads', [])
    for role in ('root', 'worker'):
        expected_pid, expected_ticks = bound_roles[role]
        if not any(
            int(row.get('pid', -1)) == expected_pid
            and int(row.get('tid', -1)) == expected_pid
            and int(row.get('start_ticks', -1)) == expected_ticks
            for row in sample_threads if isinstance(row, dict)
        ):
            raise InputError(f'Task40 CPU sample lacks the bound {role} leader identity')
    return record


def _verify_task41_process_tree(record, proc_root):
    neighbor = record['task41_neighbor']
    nodes = neighbor.get('processes')
    required_roles = {'service_wrapper', 'root', 'mpi', 'proxy', 'worker'}
    if not isinstance(nodes, list) or {node.get('role') for node in nodes} != required_roles:
        raise InputError('Task40 parallel authorization lacks the complete Task41 process chain')
    if len({int(node['pid']) for node in nodes}) != len(required_roles):
        raise InputError('Task40 parallel authorization repeats a process PID')
    by_role = {node['role']: node for node in nodes}
    anchor = neighbor.get('parent_anchor')
    if not isinstance(anchor, dict) or not isinstance(anchor.get('pid'), int):
        raise InputError('Task40 parallel authorization lacks the service parent anchor')
    if anchor.get('start_ticks') is not None:
        try:
            observed_anchor = _read_proc_identity(proc_root, anchor['pid'])
        except (OSError, ValueError, KeyError, IndexError) as exc:
            raise InputError(f'Task40 service parent anchor is unreadable: {exc}') from exc
        for key in ('start_ticks', 'ppid', 'cwd', 'argv'):
            if observed_anchor[key] != anchor.get(key):
                raise InputError(f'Task40 service parent anchor {key} differs from authorization')
        anchor_identity_verified = True
    else:
        if anchor.get('identity_status') != 'proc_visibility_denied':
            raise InputError('Task40 service parent anchor must be verified or marked unreadable')
        anchor_identity_verified = False
    expected_parent_roles = {
        'service_wrapper': None,
        'root': 'service_wrapper',
        'mpi': 'root',
        'proxy': 'mpi',
        'worker': 'proxy',
    }
    actual = {}
    missing = []
    for node in nodes:
        try:
            actual[node['role']] = _read_proc_identity(proc_root, node['pid'])
        except FileNotFoundError:
            missing.append(node['role'])
        except (OSError, ValueError, KeyError, IndexError) as exc:
            raise InputError(
                f"Task40 authorized Task41 {node['role']} identity is unreadable: {exc}"
            ) from exc
    if len(missing) == len(required_roles):
        return {
            'state': 'authorized_neighbor_cleared',
            'authorized_solver_pids': [],
            'large_process_exemption_pids': [],
            'cpu_activity_sample': None,
        }
    if missing:
        raise InputError(
            'Task40 authorized Task41 process chain is only partially present: '
            + repr(missing)
        )
    for role, expected in by_role.items():
        observed = actual[role]
        _require_bound_process_identity(observed, expected, f'Task41 {role}')
        if observed['state'] in ('Z', 'X'):
            raise InputError(f'Task40 authorized Task41 {role} is no longer active')
        parent_role = expected_parent_roles[role]
        expected_parent_pid = (
            int(anchor['pid']) if parent_role is None
            else int(by_role[parent_role]['pid'])
        )
        if observed['ppid'] != expected_parent_pid:
            raise InputError(f'Task40 authorized Task41 {role} parent chain mismatch')
    if str(neighbor.get('run_directory')) not in actual['worker']['argv']:
        raise InputError('Task40 Task41 worker argv does not bind the authorized run directory')
    if str(neighbor.get('input_path')) not in actual['root']['argv']:
        raise InputError('Task40 Task41 root argv does not bind the authorized input path')

    run_directory = Path(neighbor['run_directory'])
    manifest_path = Path(neighbor['run_manifest_path'])
    resolved_path = Path(neighbor['resolved_config_path'])
    if manifest_path.parent != run_directory or resolved_path.parent != run_directory:
        raise InputError('Task40 Task41 metadata paths are outside the bound run directory')
    try:
        manifest_raw = manifest_path.read_bytes()
        resolved_raw = resolved_path.read_bytes()
        input_path = Path(neighbor['input_path'])
        input_raw = input_path.read_bytes()
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        resolved_sha = hashlib.sha256(resolved_raw).hexdigest()
        input_sha = hashlib.sha256(input_raw).hexdigest()
        manifest = json.loads(manifest_raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f'Task40 Task41 run identity files are unreadable: {exc}') from exc
    if manifest_sha != neighbor.get('run_manifest_sha256'):
        raise InputError('Task40 Task41 run manifest changed after authorization was recorded')
    if resolved_sha != neighbor.get('resolved_config_sha256'):
        raise InputError('Task40 Task41 resolved config changed after authorization was recorded')
    if input_sha != neighbor.get('input_sha256'):
        raise InputError('Task40 Task41 input changed after authorization was recorded')
    manifest_identity = {
        'run_id': manifest.get('run_id'),
        'model_id': manifest.get('model_id'),
        'input_sha256': manifest.get('input_sha256'),
        'physical_model_sha256': manifest.get('physical_model_sha256'),
        'source_sha': manifest.get('source_sha'),
        'resolved_config_sha256': manifest.get('resolved_config_sha256'),
        'method': manifest.get('method'),
        'output_directory': manifest.get('output_directory'),
    }
    for key in (
        'run_id', 'model_id', 'input_sha256', 'physical_model_sha256',
        'source_sha', 'resolved_config_sha256',
    ):
        if manifest_identity[key] != neighbor.get(key):
            raise InputError(f'Task40 Task41 manifest {key} differs from bound run identity')
    if manifest.get('method') != 'full3d_iterative':
        raise InputError('Task40 parallel exception is restricted to the reviewed iterative Task41 run')
    if manifest.get('output_directory') != str(run_directory):
        raise InputError('Task40 Task41 manifest output path differs from bound run directory')

    cpu_activity = _sample_task41_cpu_activity(
        proc_root, [by_role['root']['pid'], by_role['worker']['pid']],
        parent_cpu=9, worker_cpus=(24,), seconds=1.0,
    )
    # Re-read the bound chain after the sample. This closes PID-reuse and
    # service-restart races during the bounded observation interval.
    for role, expected in by_role.items():
        observed = _read_proc_identity(proc_root, expected['pid'])
        _require_bound_process_identity(observed, expected, f'Task41 {role} after CPU sample')
    solver_nodes = {}
    process_nodes = {int(node['pid']): node for node in nodes}
    for role, node in by_role.items():
        classification = _classify_task40_solver_argv(node['argv'])
        if classification and classification['kind'] == 'task_solver':
            solver_nodes[int(node['pid'])] = {
                'node': node,
                'classification': classification,
            }
    return {
        'state': 'authorized_exact_neighbor_active',
        'authorized_solver_pids': sorted(solver_nodes),
        'authorized_solver_nodes': solver_nodes,
        'authorized_process_nodes': process_nodes,
        'cpu_activity_sample': cpu_activity,
        'run_identity': manifest_identity,
        'process_chain': [
            {key: by_role[role][key] for key in ('role', 'pid', 'start_ticks', 'ppid', 'cwd', 'argv')}
            for role in ('service_wrapper', 'root', 'mpi', 'proxy', 'worker')
        ],
        'parent_anchor': {**anchor, 'identity_verified': anchor_identity_verified},
    }


def _require_bound_process_identity(observed, expected, label):
    for key in ('start_ticks', 'ppid', 'cwd', 'argv'):
        if observed.get(key) != expected.get(key):
            raise InputError(f'{label} {key} differs from bound identity')


def _candidate_matches_authorized_node(candidate, authorized_node):
    node = authorized_node['node']
    if int(candidate.get('pid', -1)) != int(node['pid']):
        return False
    for key in ('start_ticks', 'ppid', 'cwd', 'argv'):
        if candidate.get(key) != node.get(key):
            return False
    return {
        key: candidate.get(key)
        for key in ('kind', 'role', 'entrypoint')
    } == authorized_node['classification']


def _sample_task41_cpu_activity(proc_root, process_ids, *, parent_cpu, worker_cpus, seconds):
    def threads():
        snapshot = []
        for pid in process_ids:
            task_root = Path(proc_root) / str(pid) / 'task'
            for task in sorted(task_root.glob('[0-9]*'), key=lambda path: int(path.name)):
                try:
                    fields = (task / 'stat').read_text().rsplit(')', 1)[1].split()
                    status = dict(
                        line.split(':', 1)
                        for line in (task / 'status').read_text().splitlines()
                        if ':' in line
                    )
                    snapshot.append({
                        'pid': int(pid), 'tid': int(task.name),
                        'start_ticks': int(fields[19]),
                        'cpu_ticks': int(fields[11]) + int(fields[12]),
                        'last_cpu': int(fields[36]),
                        'affinity': sorted(_indices(status['Cpus_allowed_list'])),
                    })
                except (OSError, ValueError, KeyError, IndexError):
                    continue
        return snapshot

    before = threads()
    started = time.monotonic()
    _sleep_for_cpu_sample(seconds)
    elapsed = time.monotonic() - started
    after = threads()
    after_by_key = {(row['pid'], row['tid']): row for row in after}
    samples = []
    for row in before:
        key = (row['pid'], row['tid'])
        later = after_by_key.get(key)
        if later is None or later['start_ticks'] != row['start_ticks']:
            samples.append({**row, 'status': 'vanished_during_sample'})
            continue
        affinity = set(row['affinity'])
        samples.append({
            **row,
            'status': 'sampled',
            'delta_cpu_ticks': later['cpu_ticks'] - row['cpu_ticks'],
            'last_cpu_after': later['last_cpu'],
            'task40_cpu9_affinity_overlap': parent_cpu in affinity,
            'task40_worker_affinity_overlap': bool(affinity.intersection(worker_cpus)),
            'sharing_permitted': True,
        })
    return {
        'sample_seconds': float(elapsed),
        'thread_samples': samples,
        'task40_parent_cpu': int(parent_cpu),
        'task40_worker_cpus': list(worker_cpus),
        'exclusive_cpu_claim': False,
        'affinity_overlap_is_authorized_sharing': True,
    }


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


def task40_host_floor_interleaved_admission(
    resources, worker_cpus, *, task_profile=None, task_run_id=None,
    parallel_authority_path=None, parallel_authority_sha256=None,
):
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

    proc_root = _proc_root()
    sys_root = _sys_root()
    status = dict(line.split(':', 1) for line in
                  (proc_root/'self/status').read_text().splitlines())
    allowed_mems = _indices(status['Mems_allowed_list'])
    if not {0, 1}.issubset(allowed_mems):
        raise InputError('Task40 interleave requires both nodes in Mems_allowed_list')
    cgroup = current_cgroup_path()
    cgroup_root = sys_root/'fs/cgroup'
    cpuset_path = cgroup
    allowed_cpus = None
    while cpuset_path is not None and cpuset_path.is_relative_to(cgroup_root):
        effective = cpuset_path/'cpuset.cpus.effective'
        if effective.is_file() and effective.read_text().strip():
            allowed_cpus = _indices(effective.read_text())
            break
        if cpuset_path == cgroup_root:
            break
        cpuset_path = cpuset_path.parent
    if allowed_cpus is None or not set(worker_cpus).issubset(allowed_cpus):
        raise InputError('Task40 worker CPUs are outside or unknown in the effective cpuset')
    cores = set()
    for cpu in worker_cpus:
        topology = sys_root/f'devices/system/cpu/cpu{cpu}/topology'
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
    if (parallel_authority_path is None) != (parallel_authority_sha256 is None):
        raise InputError('Task40 parallel authorization path and SHA256 must be supplied together')
    parallel_authority = None
    if parallel_authority_path is not None:
        record = _task40_parallel_authorization(
            parallel_authority_path, parallel_authority_sha256,
            task_profile, task_run_id,
        )
        parallel_authority = _verify_task41_process_tree(record, proc_root)
        parallel_authority.update(
            authorization_file=str(Path(parallel_authority_path).resolve()),
            authorization_sha256=str(parallel_authority_sha256).lower(),
            parent_user_authority_sha256=record.get('parent_user_authority_sha256'),
        )
    ancestors = {os.getpid()}
    current = os.getpid()
    while current > 1:
        try:
            current = _read_proc_identity(proc_root, current)['ppid']
        except (OSError, ValueError, IndexError):
            break
        if current > 1:
            ancestors.add(current)
    active_solver_candidates = []
    unknown_solver_role_candidates = []
    large = []
    for proc in proc_root.glob('[0-9]*'):
        try:
            pid = int(proc.name)
            values = dict(line.split(':', 1) for line in (proc/'status').read_text().splitlines())
            rss = int(values.get('VmRSS', '0').split()[0])*1024
            raw_argv = [part.decode('utf-8', 'replace') for part in
                        (proc/'cmdline').read_bytes().split(b'\0') if part]
            if rss >= 10_000_000_000:
                fields = (proc/'stat').read_text().rsplit(')', 1)[1].split()
                large.append({
                    'pid': pid, 'start_ticks': int(fields[19]), 'ppid': int(fields[1]),
                    'cwd': str((proc/'cwd').resolve()), 'argv': raw_argv,
                    'name': values.get('Name', '').strip(), 'rss_bytes': rss,
                })
            solver_role = _classify_task40_solver_argv(raw_argv)
            if solver_role is not None and pid not in ancestors:
                fields = (proc/'stat').read_text().rsplit(')', 1)[1].split()
                state = fields[0]
                if state not in ('Z', 'X'):
                    candidate = {
                        'pid': pid, 'start_ticks': int(fields[19]),
                        'state': state, 'rss_bytes': rss,
                        'ppid': int(fields[1]),
                        'cwd': str((proc/'cwd').resolve()),
                        'argv': raw_argv, **solver_role,
                    }
                    if solver_role['kind'] == 'task_solver':
                        active_solver_candidates.append(candidate)
                    else:
                        unknown_solver_role_candidates.append(candidate)
        except (OSError, ValueError, KeyError, IndexError):
            continue
    authorized_solver_pids = set(
        parallel_authority.get('authorized_solver_pids', [])
        if parallel_authority else []
    )
    authorized_solver_nodes = (
        parallel_authority.get('authorized_solver_nodes', {})
        if parallel_authority else {}
    )
    blocking_active_candidates = []
    blocking_unknown_candidates = []
    parallel_authorized_candidates = []
    for candidate in active_solver_candidates:
        pid = candidate['pid']
        if (parallel_authority
                and parallel_authority.get('state') == 'authorized_exact_neighbor_active'
                and pid in authorized_solver_pids
                and pid in authorized_solver_nodes
                and _candidate_matches_authorized_node(
                    candidate, authorized_solver_nodes[pid]
                )):
            parallel_authorized_candidates.append(candidate)
        else:
            blocking_active_candidates.append(candidate)
    blocking_unknown_candidates = list(unknown_solver_role_candidates)
    if parallel_authority and parallel_authority.get('state') == 'authorized_exact_neighbor_active':
        observed_parallel_pids = {row['pid'] for row in parallel_authorized_candidates}
        if observed_parallel_pids != authorized_solver_pids:
            raise InputError(
                'Task40 authorized Task41 solver roles were not all observed exactly once: '
                + repr(sorted(observed_parallel_pids))
            )
        for pid, authorized_node in authorized_solver_nodes.items():
            node = authorized_node['node']
            try:
                live = _read_proc_identity(proc_root, pid)
            except (OSError, ValueError, KeyError, IndexError) as exc:
                raise InputError(
                    f'Task40 authorized Task41 PID {pid} disappeared after solver scan: {exc}'
                ) from exc
            _require_bound_process_identity(
                live, node, f'Task41 {node.get("role")} at final solver scan'
            )
        for pid, node in parallel_authority.get('authorized_process_nodes', {}).items():
            try:
                live = _read_proc_identity(proc_root, pid)
            except (OSError, ValueError, KeyError, IndexError) as exc:
                raise InputError(
                    f'Task40 authorized Task41 PID {pid} disappeared after large-process scan: {exc}'
                ) from exc
            _require_bound_process_identity(
                live, node, f'Task41 {node.get("role")} at final large-process scan'
            )
    if blocking_active_candidates:
        raise InputError(
            'Task40 admission found another active run_case/native solver process: '
            + repr(blocking_active_candidates)
        )
    if blocking_unknown_candidates:
        raise InputError(
            'Task40 admission found an active Task038/P6 Python entrypoint with unknown role: '
            + repr(blocking_unknown_candidates)
        )
    parallel_process_nodes = (
        parallel_authority.get('authorized_process_nodes', {})
        if parallel_authority else {}
    )
    blocking_large = [
        row for row in large
        if row['rss_bytes'] >= 100_000_000_000
        and not (
            parallel_authority
            and parallel_authority.get('state') == 'authorized_exact_neighbor_active'
            and row['pid'] in parallel_process_nodes
            and all(row.get(key) == parallel_process_nodes[row['pid']].get(key)
                    for key in ('start_ticks', 'ppid', 'cwd', 'argv'))
        )
    ]
    if blocking_large:
        raise InputError(
            'Task40 admission found a non-authorized process >=100 GB; no heavy launch: '
            + repr(blocking_large)
        )

    probe = _interleave_probe()
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
                'meminfo': (sys_root/f'devices/system/node/node{node}/meminfo').read_text().splitlines()[:5],
                'cpus': (sys_root/f'devices/system/node/node{node}/cpulist').read_text().strip(),
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
        'blocking_large_processes': blocking_large,
        'active_solver_candidates': active_solver_candidates,
        'parallel_authorized_solver_candidates': parallel_authorized_candidates,
        'blocking_active_solver_candidates': blocking_active_candidates,
        'unknown_solver_role_candidates': unknown_solver_role_candidates,
        'parallel_neighbor_authorization': parallel_authority,
        'parallel_neighbor_authorized': bool(
            parallel_authority
            and parallel_authority.get('state') == 'authorized_exact_neighbor_active'
        ),
        'user_parallel_window_authorization': bool(
            parallel_authority
            and parallel_authority.get('state') == 'authorized_exact_neighbor_active'
        ),
        'interleave_probe_maps': maps,
        'worktree_disk_free_bytes_at_admission': disk.free,
        'neighbors_modified': False,
        'legacy_launch_cap_used_for_admission': False,
    }
