'''Bounded rank-local NUMA evidence for explicit Task041 cell-condensed cases.'''

from __future__ import annotations

import ctypes
import json
import mmap
import os
import re
from collections.abc import Mapping, Sequence
from numbers import Integral
from pathlib import Path
from typing import Any

import numpy as np

_PAGE_BYTES = 4096
_PROBE_BYTES = 64 * 1024
_BACKGROUND_LIMIT = 8
_MATH_THREAD_ENV_NAMES = (
    'OMP_NUM_THREADS',
    'OPENBLAS_NUM_THREADS',
    'MKL_NUM_THREADS',
    'NUMEXPR_NUM_THREADS',
    'VECLIB_MAXIMUM_THREADS',
)
_V13_MATH_THREAD_ENV_NAMES = _MATH_THREAD_ENV_NAMES + ('BLIS_NUM_THREADS',)
TASK041_V13_DEFAULT_MEMORY_POLICY = 'system_default_unbound'


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"NUMA evidence contains a non-JSON value: {type(value).__name__}")


def _process_identity() -> dict[str, Any]:
    pid = os.getpid()
    stat_text = Path(f'/proc/{pid}/stat').read_text(encoding='utf-8').strip()
    _comm, stat_tail = stat_text.rsplit(')', 1)
    stat_fields = stat_tail.split()
    if len(stat_fields) <= 19:
        raise OSError('/proc/self/stat has no starttime field')
    affinity = sorted(int(cpu) for cpu in os.sched_getaffinity(0))
    current_cpu = (
        int(stat_fields[36]) if len(stat_fields) > 36 else None
    )
    topology = []
    for cpu in affinity:
        cpu_root = Path(f'/sys/devices/system/cpu/cpu{cpu}')
        socket = int(
            (cpu_root / 'topology/physical_package_id').read_text(
                encoding='utf-8'
            ).strip()
        )
        nodes = sorted(
            int(path.name[4:]) for path in cpu_root.glob('node[0-9]*')
        )
        if not nodes:
            raise OSError(f'CPU {cpu} has no readable NUMA node mapping')
        topology.append(
            {'os_cpu': int(cpu), 'socket': socket, 'numa_nodes': nodes}
        )
    return {
        'pid': int(pid),
        'ppid': int(stat_fields[1]),
        'pgid': int(stat_fields[2]),
        'sid': int(stat_fields[3]),
        'starttime_ticks': int(stat_fields[19]),
        'clock_ticks': int(os.sysconf('SC_CLK_TCK')),
        'current_cpu': current_cpu,
        'sched_getaffinity': affinity,
        'cpu_topology': topology,
    }


def _math_thread_environment(
    required_names: Sequence[str] = _MATH_THREAD_ENV_NAMES,
) -> dict[str, Any]:
    variables = {
        name: os.environ.get(name) for name in required_names
    }
    complete = all(value is not None for value in variables.values())
    return {
        'status': 'measured' if complete else 'not_observed',
        'variables': variables,
        'all_one': bool(complete and all(value == '1' for value in variables.values())),
    }


def append_stage_jsonl(
    comm: Any,
    path: str | Path,
    record: Mapping[str, Any],
) -> None:
    """Append one rank-zero evidence record and broadcast write failures."""

    write_error = None
    if comm.rank == 0:
        try:
            encoded = json.dumps(
                record,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
                default=_json_default,
            )
            with Path(path).open("a", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except Exception as exc:  # noqa: BLE001 - broadcast root I/O failures
            write_error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
    write_error = comm.bcast(write_error, root=0)
    if write_error is not None:
        raise OSError(
            "Task041 NUMA evidence JSONL write failed: "
            f"{write_error['type']}: {write_error['message']}"
        )


def _mempolicy_snapshot() -> dict[str, Any]:
    libnuma = ctypes.CDLL('libnuma.so.1', use_errno=True)
    get_mempolicy = libnuma.get_mempolicy
    get_mempolicy.argtypes = [
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    get_mempolicy.restype = ctypes.c_int
    maxnode = 1024
    word_bits = ctypes.sizeof(ctypes.c_ulong) * 8
    words = (maxnode + word_bits - 1) // word_bits
    mask = (ctypes.c_ulong * words)()
    mode = ctypes.c_int()
    rc = int(
        get_mempolicy(
            ctypes.byref(mode),
            mask,
            ctypes.c_ulong(maxnode),
            None,
            0,
        )
    )
    if rc != 0:
        raise OSError(ctypes.get_errno(), 'get_mempolicy failed')
    nodes = [
        index
        for index in range(maxnode)
        if mask[index // word_bits] & (1 << (index % word_bits))
    ]
    return {
        'status': 'measured',
        'mode': int(mode.value),
        'policy': 'default' if mode.value == 0 else 'nondefault',
        'effective_nodemask': nodes,
    }


def _parse_node_list(value: str) -> list[int]:
    nodes: set[int] = set()
    for item in value.strip().split(','):
        if not item:
            raise ValueError('node list contains an empty component')
        bounds = item.split('-', 1)
        if len(bounds) == 1:
            start = end = int(bounds[0])
        else:
            start, end = (int(part) for part in bounds)
        if start < 0 or end < start:
            raise ValueError('node list contains an invalid range')
        nodes.update(range(start, end + 1))
    if not nodes:
        raise ValueError('node list is empty')
    return sorted(nodes)


def _unescape_mount_field(value: str) -> str:
    return re.sub(r'\\([0-7]{3})', lambda match: chr(int(match.group(1), 8)), value)


def _resolve_cgroup_v2_identity(proc_root: Path) -> dict[str, str]:
    cgroup_rows = []
    for line in (proc_root / 'self/cgroup').read_text(encoding='ascii').splitlines():
        fields = line.split(':', 2)
        if len(fields) == 3 and fields[0] == '0' and fields[1] == '':
            cgroup_rows.append(fields[2])
    if len(cgroup_rows) != 1:
        raise ValueError('unified cgroup path is missing or ambiguous')
    cgroup_path = cgroup_rows[0]
    if not cgroup_path.startswith('/') or cgroup_path.endswith(' (deleted)'):
        raise ValueError('unified cgroup path is not a live absolute path')
    cgroup_parts = [] if cgroup_path == '/' else cgroup_path[1:].split('/')
    if any(part in {'', '.', '..'} for part in cgroup_parts):
        raise ValueError('unified cgroup path contains an unsafe component')

    mounts = []
    for line in (proc_root / 'self/mountinfo').read_text(encoding='ascii').splitlines():
        left, separator, right = line.partition(' - ')
        if not separator:
            continue
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 5 or not right_fields or right_fields[0] != 'cgroup2':
            continue
        mount_root = _unescape_mount_field(left_fields[3])
        mount_point = _unescape_mount_field(left_fields[4])
        if not mount_root.startswith('/') or not mount_point.startswith('/'):
            raise ValueError('cgroup2 mount mapping is not absolute')
        normalized_root = mount_root.rstrip('/') or '/'
        if cgroup_path == normalized_root:
            relative = ''
        elif normalized_root == '/':
            relative = cgroup_path.lstrip('/')
        elif cgroup_path.startswith(normalized_root + '/'):
            relative = cgroup_path[len(normalized_root):].lstrip('/')
        else:
            continue
        mounts.append((len(normalized_root), normalized_root, mount_point, relative))
    if not mounts:
        raise ValueError('visible cgroup2 mount does not cover the process cgroup')
    longest = max(row[0] for row in mounts)
    candidates = [row for row in mounts if row[0] == longest]
    if len(candidates) != 1:
        raise ValueError('visible cgroup2 mount mapping is ambiguous')
    _, mount_root, mount_point, relative = candidates[0]
    relative_parts = [] if not relative else relative.split('/')
    if any(part in {'', '.', '..'} for part in relative_parts):
        raise ValueError('cgroup-relative path contains an unsafe component')
    mount_base = Path(mount_point).resolve(strict=True)
    cgroup_directory = (mount_base / relative).resolve(strict=True)
    if cgroup_directory != mount_base and mount_base not in cgroup_directory.parents:
        raise ValueError('resolved cgroup path escaped the visible mount')
    return {
        'unified_path': cgroup_path,
        'mount_root': mount_root,
        'mount_point': str(mount_base),
        'resolved_mount_point': str(mount_base),
        'resolved_cgroup_directory': str(cgroup_directory),
    }


def _memory_scope_snapshot(proc_root: Path = Path('/proc')) -> dict[str, Any]:
    """Bind Mems_allowed_list to the direct or proven inherited cgroup v2 set."""

    result: dict[str, Any] = {
        'status': 'not_observed',
        'proc_status_mems_allowed_list': None,
        'proc_allowed_nodes': None,
        'cgroup_identity_before': None,
        'cgroup_identity_after': None,
        'cgroup_identity_stable': False,
        'effective_nodes': None,
        'effective_source_kind': None,
        'effective_source_path': None,
        'effective_source_cgroup_path': None,
        'inheritance_reason': None,
        'controller_walk': [],
        'inheritance_edges': [],
        'allowed_nodes_match': False,
        'errors': [],
        'pass': False,
    }
    identity_before = None
    try:
        status_lines = (proc_root / 'self/status').read_text(encoding='ascii').splitlines()
        allowed_rows = [
            line.split(':', 1)[1].strip()
            for line in status_lines
            if line.startswith('Mems_allowed_list:')
        ]
        if len(allowed_rows) != 1:
            raise ValueError('Mems_allowed_list is missing or ambiguous')
        allowed_nodes = _parse_node_list(allowed_rows[0])
        result['proc_status_mems_allowed_list'] = allowed_rows[0]
        result['proc_allowed_nodes'] = allowed_nodes
        identity_before = _resolve_cgroup_v2_identity(proc_root)
        result['cgroup_identity_before'] = identity_before
        cgroup_directory = Path(identity_before['resolved_cgroup_directory'])
        mount_base = Path(identity_before['resolved_mount_point'])
        mount_root = identity_before['mount_root']

        def logical_path(directory: Path) -> str:
            relative = directory.relative_to(mount_base).as_posix()
            if relative == '.':
                return mount_root
            if mount_root == '/':
                return '/' + relative
            return mount_root.rstrip('/') + '/' + relative

        observed: dict[Path, dict[str, Any]] = {}

        def observe(directory: Path) -> dict[str, Any]:
            if directory in observed:
                return observed[directory]
            controllers_raw = (directory / 'cgroup.controllers').read_text(encoding='ascii')
            subtree_raw = (directory / 'cgroup.subtree_control').read_text(encoding='ascii')
            controllers = controllers_raw.split()
            subtree = subtree_raw.split()
            if (
                len(controllers) != len(set(controllers))
                or len(subtree) != len(set(subtree))
                or any(re.fullmatch(r'[A-Za-z0-9_]+', item) is None
                       for item in controllers + subtree)
            ):
                raise ValueError('cgroup controller list is malformed')
            row = {
                'cgroup_path': logical_path(directory),
                'filesystem_path': str(directory),
                'cgroup_controllers': controllers,
                'cgroup_subtree_control': subtree,
                'cpuset_enabled_for_children': 'cpuset' in subtree,
                'cpuset_mems_effective_path': str(directory / 'cpuset.mems.effective'),
                'cpuset_mems_effective_status': 'not_read',
            }
            observed[directory] = row
            result['controller_walk'].append(row)
            return row

        leaf_path = cgroup_directory / 'cpuset.mems.effective'
        result['cpuset_mems_effective_path'] = str(leaf_path)
        try:
            effective_text = leaf_path.read_text(encoding='ascii').strip()
        except FileNotFoundError:
            effective_text = None
        if effective_text is not None:
            if not effective_text:
                raise ValueError('leaf cpuset.mems.effective is empty')
            result['effective_source_kind'] = 'direct_leaf'
            result['effective_source_path'] = str(leaf_path)
            result['effective_source_cgroup_path'] = logical_path(cgroup_directory)
        else:
            child = observe(cgroup_directory)
            child['cpuset_mems_effective_status'] = 'missing'
            if 'cpuset' in child['cgroup_controllers']:
                raise ValueError('leaf cpuset controller is active but its effective file is missing')
            current = cgroup_directory
            while current != mount_base:
                parent = current.parent
                if parent == current or (parent != mount_base and mount_base not in parent.parents):
                    raise ValueError('cpuset inheritance walk escaped the visible mount')
                parent_row = observe(parent)
                child_available = 'cpuset' in child['cgroup_controllers']
                parent_enabled = parent_row['cpuset_enabled_for_children']
                result['inheritance_edges'].append({
                    'parent_cgroup_path': parent_row['cgroup_path'],
                    'child_cgroup_path': child['cgroup_path'],
                    'parent_subtree_control_enables_cpuset': parent_enabled,
                    'child_cgroup_controllers_lists_cpuset': child_available,
                })
                if parent_enabled != child_available:
                    raise ValueError('cpuset inheritance records contradict')
                if parent_enabled:
                    raise ValueError('cpuset is enabled for child but its effective file is missing')
                current = parent
                child = parent_row
                effective_path = current / 'cpuset.mems.effective'
                try:
                    effective_text = effective_path.read_text(encoding='ascii').strip()
                except FileNotFoundError:
                    child['cpuset_mems_effective_status'] = 'missing'
                    if 'cpuset' in child['cgroup_controllers'] or current == mount_base:
                        raise ValueError('no valid ancestor cpuset.mems.effective source exists')
                    continue
                if not effective_text:
                    raise ValueError('ancestor cpuset.mems.effective is empty')
                if 'cpuset' not in child['cgroup_controllers']:
                    raise ValueError('ancestor effective file lacks cpuset controller evidence')
                child['cpuset_mems_effective_status'] = 'present'
                result['effective_source_kind'] = 'inherited_ancestor'
                result['effective_source_path'] = str(effective_path)
                result['effective_source_cgroup_path'] = logical_path(current)
                result['inheritance_reason'] = (
                    'Traversed parent subtree_control and child cgroup.controllers exclude cpuset; '
                    'the nearest visible ancestor effective file supplies the inherited set.'
                )
                break
            if effective_text is None:
                raise ValueError('no ancestor cpuset.mems.effective source was found')
        effective_nodes = _parse_node_list(effective_text)
        result['effective_nodes'] = effective_nodes
        result['allowed_nodes_match'] = allowed_nodes == effective_nodes
        if not result['allowed_nodes_match']:
            raise ValueError('Mems_allowed_list differs from the effective cgroup cpuset nodes')
        result['status'] = 'measured'
    except (OSError, ValueError, IndexError, RuntimeError) as exc:
        result['errors'].append({'type': type(exc).__name__, 'message': str(exc)[:240]})
    try:
        identity_after = _resolve_cgroup_v2_identity(proc_root)
        result['cgroup_identity_after'] = identity_after
        result['cgroup_identity_stable'] = (
            identity_before is not None and identity_before == identity_after
        )
        if not result['cgroup_identity_stable']:
            result['errors'].append({
                'type': 'CgroupIdentityChanged',
                'message': 'cgroup identity changed across the memory-scope sample',
            })
    except (OSError, ValueError, IndexError, RuntimeError) as exc:
        result['errors'].append({
            'type': type(exc).__name__,
            'message': ('post-sample cgroup identity: ' + str(exc))[:240],
        })
    result['pass'] = bool(
        result['status'] == 'measured'
        and result['allowed_nodes_match'] is True
        and result['cgroup_identity_stable'] is True
        and not result['errors']
    )
    return result


def _mapping_line(address: int) -> dict[str, Any]:
    mapping = None
    with Path('/proc/self/maps').open(encoding='utf-8') as stream:
        for line in stream:
            fields = line.split()
            start, end = (
                int(value, 16) for value in fields[0].split('-', 1)
            )
            if start <= address < end:
                permissions = fields[1]
                path = ' '.join(fields[5:]) if len(fields) > 5 else ''
                private = permissions[3:4] == 'p'
                file_backed = bool(
                    path and not path.startswith(('[heap]', '[stack]', '[anon'))
                )
                mapping = {
                    'status': 'measured',
                    'start': start,
                    'end': end,
                    'permissions': permissions,
                    'private': private,
                    'file_backed': file_backed,
                    'mapping_kind': (
                        'private_file'
                        if private and file_backed
                        else 'private_anon_or_anonymous'
                        if private
                        else 'shared_or_file'
                    ),
                    'raw': line.rstrip()[:512],
                }
                break
    if mapping is None:
        return {'status': 'not_observed', 'address': int(address)}
    node_pages: dict[str, int] = {}
    numa_raw = None
    with Path('/proc/self/numa_maps').open(encoding='utf-8') as stream:
        for line in stream:
            first = line.split(maxsplit=1)[0]
            if int(first, 16) != int(mapping['start']):
                continue
            numa_raw = line.rstrip()[:1024]
            for field in line.split()[1:]:
                if field.startswith('N') and '=' in field:
                    name, value = field.split('=', 1)
                    try:
                        node_pages[name] = int(value)
                    except ValueError:
                        pass
            break
    mapping['numa_maps'] = numa_raw if numa_raw is not None else 'not_observed'
    mapping['node_pages'] = node_pages or None
    mapping['vma_aggregation'] = True
    return mapping


def _array_memory_mapping(name: str, value: object) -> dict[str, Any]:
    raw = value.getArray(readonly=True) if hasattr(value, 'getArray') else value
    array = np.asarray(raw)
    if array.nbytes == 0:
        return {
            'object': str(name),
            'address': None,
            'bytes': 0,
            'pages': 0,
            'dtype': str(array.dtype),
            'empty_owner': True,
            'vma_aggregation': True,
            'mapping': {
                'status': 'not_applicable',
                'reason': 'empty_owner_no_local_pages',
            },
        }
    address = int(array.__array_interface__['data'][0])
    mapping = _mapping_line(address)
    return {
        'object': str(name),
        'address': address,
        'bytes': int(array.nbytes),
        'pages': int((array.nbytes + _PAGE_BYTES - 1) // _PAGE_BYTES),
        'dtype': str(array.dtype),
        'empty_owner': False,
        'vma_aggregation': True,
        'mapping': mapping,
    }


def _private_anon_samples(limit: int = _BACKGROUND_LIMIT) -> list[dict[str, Any]]:
    mappings: dict[int, dict[str, Any]] = {}
    with Path('/proc/self/maps').open(encoding='utf-8') as stream:
        for line in stream:
            fields = line.split()
            start = int(fields[0].split('-', 1)[0], 16)
            permissions = fields[1]
            path = ' '.join(fields[5:]) if len(fields) > 5 else ''
            mappings[start] = {
                'private': permissions[3:4] == 'p',
                'path': path,
                'file_backed': bool(
                    path and not path.startswith(('[heap]', '[stack]', '[anon'))
                ),
            }
    candidates = []
    with Path('/proc/self/numa_maps').open(encoding='utf-8') as stream:
        for line in stream:
            fields = line.split()
            start = int(fields[0], 16)
            mapping = mappings.get(start)
            if mapping is None or not mapping['private'] or 'file=' in line:
                continue
            if not any(
                field.startswith(('anon=', 'heap', 'stack'))
                for field in fields[1:]
            ):
                continue
            anon_pages = next(
                (int(field.split('=', 1)[1]) for field in fields[1:]
                 if field.startswith('anon=')),
                None,
            )
            nodes = {}
            for field in fields[1:]:
                if field.startswith('N') and '=' in field:
                    key, value = field.split('=', 1)
                    try:
                        nodes[key] = int(value)
                    except ValueError:
                        pass
            candidates.append({
                'mapping_start': start,
                'anon_pages': anon_pages,
                'nodes': nodes or None,
                'private': True,
                'file_backed': bool(mapping['file_backed']),
                'path': mapping['path'],
                'raw': line.rstrip()[:1024],
                'vma_aggregation': True,
            })
    candidates.sort(
        key=lambda item: (
            item['anon_pages'] is None,
            -int(item['anon_pages'] or 0),
            int(item['mapping_start']),
        )
    )
    return candidates[:int(limit)]


def snapshot(
    stage: str,
    arrays: Mapping[str, object] | None = None,
    *,
    include_probe: bool = True,
    include_memory_scope: bool = False,
    thread_environment_names: Sequence[str] = _MATH_THREAD_ENV_NAMES,
) -> dict[str, Any]:
    probe = None
    try:
        probe_evidence: dict[str, Any] = {
            'status': 'not_applicable',
            'reason': 'startup_only_probe',
        }
        if include_probe:
            probe = mmap.mmap(
                -1,
                _PROBE_BYTES,
                flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
                prot=mmap.PROT_READ | mmap.PROT_WRITE,
            )
            for offset in range(0, _PROBE_BYTES, _PAGE_BYTES):
                probe[offset] = 1
            probe_address = ctypes.addressof(
                ctypes.c_char.from_buffer(probe)
            )
            probe_evidence = {
                'address': int(probe_address),
                'bytes': _PROBE_BYTES,
                'pages': _PROBE_BYTES // _PAGE_BYTES,
                'first_touch': True,
                'mapping': _mapping_line(probe_address),
            }
        return {
            'schema': 'task041.rank_numa_snapshot.v1',
            'stage': str(stage),
            'rank_identity': _process_identity(),
            'task_policy': _mempolicy_snapshot(),
            'math_thread_environment': _math_thread_environment(
                thread_environment_names
            ),
            'memory_scope': (
                _memory_scope_snapshot() if include_memory_scope else None
            ),
            'short_private_probe': probe_evidence,
            'objects': [
                _array_memory_mapping(name, value)
                for name, value in (arrays or {}).items()
            ],
            'private_anon_background': _private_anon_samples(),
            'memory_mapping_scope': 'VMA aggregation; not per-object page ownership',
        }
    finally:
        if probe is not None:
            probe.close()


def collective_snapshot(
    comm: Any,
    stage: str,
    arrays: Mapping[str, object] | None = None,
    *,
    include_probe: bool = True,
    include_memory_scope: bool = False,
    thread_environment_names: Sequence[str] = _MATH_THREAD_ENV_NAMES,
) -> dict[str, Any]:
    local_error = None
    try:
        local = snapshot(
            stage,
            arrays,
            include_probe=include_probe,
            include_memory_scope=include_memory_scope,
            thread_environment_names=thread_environment_names,
        )
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        local = {
            'schema': 'task041.rank_numa_snapshot.v1',
            'stage': str(stage),
            'status': 'not_observed',
        }
        local_error = f'{type(exc).__name__}: {exc}'
    errors = comm.allgather(local_error)
    return {
        'rank': int(comm.rank),
        'stage': str(stage),
        'collective_status': 'measured' if not any(errors) else 'failed',
        'rank_error': local_error,
        'rank_errors': errors if any(errors) else None,
        'evidence': local,
    }


def _check_private_resident_mapping(
    label: str,
    mapping: object,
    errors: list[str],
    *,
    expected_node: str | None = 'N0',
) -> None:
    if not isinstance(mapping, Mapping):
        errors.append(f'{label} mapping is missing')
        return
    if mapping.get('status') != 'measured':
        errors.append(f'{label} mapping is not observed')
        return
    if mapping.get('private') is not True or mapping.get('file_backed') is True:
        errors.append(f'{label} is not private anonymous memory')
    node_pages = mapping.get('node_pages')
    if not isinstance(node_pages, Mapping):
        errors.append(f'{label} resident node pages are not observed')
        return
    resident = {
        str(name): int(value)
        for name, value in node_pages.items()
        if isinstance(value, int) and int(value) > 0
    }
    if sum(resident.values()) <= 0:
        errors.append(f'{label} has no measured resident pages')
    if expected_node is not None and any(name != expected_node for name in resident):
        errors.append(f'{label} has resident pages outside {expected_node}')


def normalize_expected_rank_cpus(
    expected_rank_cpus: Sequence[int] | None,
    *,
    expected_mpi_size: int,
) -> tuple[int, ...]:
    """Freeze a rank-to-CPU map, preserving the historical 1-based default."""

    if type(expected_mpi_size) is not int or expected_mpi_size <= 0:
        raise ValueError('expected MPI size must be a positive integer')
    if expected_rank_cpus is None:
        return tuple(range(1, expected_mpi_size + 1))
    if isinstance(expected_rank_cpus, (str, bytes, bytearray)) or not isinstance(
        expected_rank_cpus, Sequence
    ):
        raise TypeError('expected rank CPUs must be a finite sequence')
    if len(expected_rank_cpus) != expected_mpi_size:
        raise ValueError(
            'expected rank CPU map length must equal the MPI size '
            f'({expected_mpi_size})'
        )
    if any(
        isinstance(cpu, (bool, np.bool_)) or not isinstance(cpu, Integral)
        for cpu in expected_rank_cpus
    ):
        raise ValueError('expected rank CPUs must be non-boolean integers')
    cpus = tuple(int(cpu) for cpu in expected_rank_cpus)
    if any(cpu < 0 for cpu in cpus):
        raise ValueError('expected rank CPUs must be nonnegative')
    if len(set(cpus)) != expected_mpi_size:
        raise ValueError('expected rank CPUs must be unique')
    return cpus


def qualification_errors(
    payload: Mapping[str, Any],
    *,
    expected_mpi_size: int,
    previous_identities: Mapping[int, tuple[int, int]],
    require_startup_probe: bool,
    expected_rank_cpus: Sequence[int] | None = None,
    expected_memory_policy: str | None = None,
    previous_process_identities: Mapping[int, tuple[int, int, int, int, int]] | None = None,
) -> list[str]:
    errors: list[str] = []
    if expected_memory_policy not in (None, TASK041_V13_DEFAULT_MEMORY_POLICY):
        errors.append("requested memory policy is unsupported")
    v13_default_policy = (
        expected_memory_policy == TASK041_V13_DEFAULT_MEMORY_POLICY
    )
    try:
        expected_cpus = normalize_expected_rank_cpus(
            expected_rank_cpus,
            expected_mpi_size=int(expected_mpi_size),
        )
    except (TypeError, ValueError) as exc:
        return [f'expected rank CPU map is invalid: {exc}']
    if payload.get('mpi_size') != int(expected_mpi_size):
        errors.append('mpi_size is not the expected MPI8 size')
    ranks = payload.get('ranks')
    if not isinstance(ranks, list) or len(ranks) != int(expected_mpi_size):
        return errors + ['rank evidence is incomplete']
    seen: set[int] = set()
    for item in ranks:
        rank = item.get('rank') if isinstance(item, Mapping) else None
        if type(rank) is not int or rank in seen or rank < 0:
            errors.append('rank identity list is malformed')
            continue
        seen.add(rank)
        if rank >= int(expected_mpi_size):
            errors.append(f'rank {rank} is outside the expected MPI range')
            continue
        evidence = item.get('evidence')
        if not isinstance(evidence, Mapping):
            errors.append(f'rank {rank} evidence is missing')
            continue
        identity = evidence.get('rank_identity')
        if not isinstance(identity, Mapping):
            errors.append(f'rank {rank} process identity is missing')
            continue
        v13_default = v13_default_policy
        expected_cpu = expected_cpus[rank]
        if identity.get('sched_getaffinity') != [expected_cpu]:
            errors.append(f'rank {rank} affinity is not CPU {expected_cpu}')
        if identity.get('current_cpu') != expected_cpu:
            errors.append(f'rank {rank} current CPU is not {expected_cpu}')
        topology = identity.get('cpu_topology')
        cpu_record = next(
            (row for row in topology or []
             if row.get('os_cpu') == expected_cpu),
            None,
        )
        if (
            not isinstance(cpu_record, Mapping)
            or cpu_record.get('socket') != 0
            or 0 not in cpu_record.get('numa_nodes', [])
        ):
            errors.append(f'rank {rank} CPU topology is not socket0/node0')
        policy = evidence.get('task_policy')
        if v13_default:
            if (
                not isinstance(policy, Mapping)
                or policy.get('status') != 'measured'
                or policy.get('mode') != 0
                or policy.get('policy') != 'default'
            ):
                errors.append(f'rank {rank} task policy is not MPOL_DEFAULT')
            memory_scope = evidence.get('memory_scope')
            allowed_nodes = (
                memory_scope.get('proc_allowed_nodes')
                if isinstance(memory_scope, Mapping)
                else None
            )
            effective_nodes = (
                memory_scope.get('effective_nodes')
                if isinstance(memory_scope, Mapping)
                else None
            )

            def valid_node_scope(value: Any) -> bool:
                return bool(
                    isinstance(value, list)
                    and value
                    and all(type(node) is int and node >= 0 for node in value)
                    and value == sorted(set(value))
                )

            if (
                not isinstance(memory_scope, Mapping)
                or memory_scope.get('status') != 'measured'
                or memory_scope.get('pass') is not True
                or memory_scope.get('allowed_nodes_match') is not True
                or memory_scope.get('cgroup_identity_stable') is not True
                or not valid_node_scope(allowed_nodes)
                or not valid_node_scope(effective_nodes)
                or allowed_nodes != effective_nodes
            ):
                errors.append(
                    f'rank {rank} Mems_allowed_list/cgroup scope is not qualified'
                )
        elif (
            not isinstance(policy, Mapping)
            or policy.get('status') != 'measured'
            or policy.get('mode') != 2
            or policy.get('effective_nodemask') != [0]
        ):
            errors.append(f'rank {rank} task policy is not MPOL_BIND node0')
        threads = evidence.get('math_thread_environment')
        if (
            not isinstance(threads, Mapping)
            or threads.get('status') != 'measured'
            or threads.get('all_one') is not True
        ):
            errors.append(f'rank {rank} math thread environment is not all one')
        elif v13_default and (
            not isinstance(threads.get('variables'), Mapping)
            or set(threads['variables']) != set(_V13_MATH_THREAD_ENV_NAMES)
            or any(value != '1' for value in threads['variables'].values())
        ):
            errors.append(f'rank {rank} six mathematical thread controls are incomplete')
        current_identity = (
            identity.get('pid'),
            identity.get('starttime_ticks'),
        )
        if not all(isinstance(value, int) for value in current_identity):
            errors.append(f'rank {rank} PID/starttime is not measured')
        elif (
            rank in previous_identities
            and previous_identities[rank] != current_identity
        ):
            errors.append(f'rank {rank} PID/starttime changed')
        if v13_default:
            process_identity = (
                identity.get('pid'),
                identity.get('ppid'),
                identity.get('pgid'),
                identity.get('sid'),
                identity.get('starttime_ticks'),
            )
            if (
                type(process_identity[0]) is not int
                or process_identity[0] <= 0
                or type(process_identity[1]) is not int
                or process_identity[1] < 0
                or any(
                    type(value) is not int or value <= 0
                    for value in process_identity[2:]
                )
            ):
                errors.append(f'rank {rank} PPID/PGID/SID identity is incomplete')
            elif (
                previous_process_identities is not None
                and rank in previous_process_identities
                and previous_process_identities[rank] != process_identity
            ):
                errors.append(f'rank {rank} process/session identity changed')
        probe = evidence.get('short_private_probe')
        if require_startup_probe:
            probe_mapping = (
                probe.get('mapping')
                if isinstance(probe, Mapping)
                else None
            )
            _check_private_resident_mapping(
                'rank probe',
                probe_mapping,
                errors,
                expected_node=None if v13_default else 'N0',
            )
        elif isinstance(probe, Mapping) and probe.get('status') != 'not_applicable':
            errors.append(f'rank {rank} has an unexpected later probe')
        objects = evidence.get('objects')
        if not isinstance(objects, list):
            errors.append(f'rank {rank} object evidence is missing')
        else:
            if not require_startup_probe and not objects:
                errors.append(f'rank {rank} real object evidence is empty')
            for obj in objects:
                if not isinstance(obj, Mapping):
                    errors.append(f'rank {rank} object evidence is malformed')
                    continue
                if obj.get('bytes') == 0:
                    if obj.get('empty_owner') is not True:
                        errors.append(f'rank {rank} zero object lacks empty-owner marker')
                    continue
                _check_private_resident_mapping(
                    'rank object',
                    obj.get('mapping'),
                    errors,
                    expected_node=None if v13_default else 'N0',
                )
    if seen != set(range(int(expected_mpi_size))):
        errors.append('not every expected rank supplied evidence')
    return errors
