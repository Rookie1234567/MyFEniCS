'''Bounded rank-local NUMA evidence for explicit Task041 cell-condensed cases.'''

from __future__ import annotations

import ctypes
import json
import mmap
import os
from collections.abc import Mapping
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
        'starttime_ticks': int(stat_fields[19]),
        'clock_ticks': int(os.sysconf('SC_CLK_TCK')),
        'current_cpu': current_cpu,
        'sched_getaffinity': affinity,
        'cpu_topology': topology,
    }


def _math_thread_environment() -> dict[str, Any]:
    variables = {
        name: os.environ.get(name) for name in _MATH_THREAD_ENV_NAMES
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
        'effective_nodemask': nodes,
    }


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
            'math_thread_environment': _math_thread_environment(),
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
) -> dict[str, Any]:
    local_error = None
    try:
        local = snapshot(stage, arrays, include_probe=include_probe)
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
    if any(name != 'N0' for name in resident):
        errors.append(f'{label} has resident pages outside node0')


def qualification_errors(
    payload: Mapping[str, Any],
    *,
    expected_mpi_size: int,
    previous_identities: Mapping[int, tuple[int, int]],
    require_startup_probe: bool,
) -> list[str]:
    errors: list[str] = []
    if payload.get('mpi_size') != int(expected_mpi_size):
        errors.append('mpi_size is not the expected MPI8 size')
    ranks = payload.get('ranks')
    if not isinstance(ranks, list) or len(ranks) != int(expected_mpi_size):
        return errors + ['rank evidence is incomplete']
    seen: set[int] = set()
    for item in ranks:
        rank = item.get('rank') if isinstance(item, Mapping) else None
        if not isinstance(rank, int) or rank in seen or rank < 0:
            errors.append('rank identity list is malformed')
            continue
        seen.add(rank)
        evidence = item.get('evidence')
        if not isinstance(evidence, Mapping):
            errors.append(f'rank {rank} evidence is missing')
            continue
        identity = evidence.get('rank_identity')
        if not isinstance(identity, Mapping):
            errors.append(f'rank {rank} process identity is missing')
            continue
        expected_cpu = rank + 1
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
        if (
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
        probe = evidence.get('short_private_probe')
        if require_startup_probe:
            probe_mapping = (
                probe.get('mapping')
                if isinstance(probe, Mapping)
                else None
            )
            _check_private_resident_mapping(
                'rank probe', probe_mapping, errors
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
                _check_private_resident_mapping('rank object', obj.get('mapping'), errors)
    if seen != set(range(int(expected_mpi_size))):
        errors.append('not every expected rank supplied evidence')
    return errors
