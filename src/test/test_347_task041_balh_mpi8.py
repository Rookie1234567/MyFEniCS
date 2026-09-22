'''Focused MPI8 real-side old/full versus cell-condensed qualification.'''

from __future__ import annotations

import ctypes
import hashlib
import json
import mmap
import os
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.geometry.hybrid_local_mesh import build_hybrid_local_mesh
from src.solvers.hybrid_local_dtn_action import (
    assemble_hybrid_local_dtn_action_system,
)
from src.solvers.physical_balanced_side_inverse import (
    build_side_balanced_inverse,
)
from src.solvers.physical_balanced_trace_bridge import (
    inject_active_residual_to_full_p6,
)
from src.test.test_347_task041_balh_physical_operator import (
    _fill_active,
    _fixture_config,
)

pytestmark = pytest.mark.skipif(
    MPI.COMM_WORLD.size != 8,
    reason='This targeted qualification node requires exactly MPI8',
)

_Q_TOLERANCE = 1.0e-11
_PC_TOLERANCE = 1.0e-8
_A4_TOLERANCE = 1.0e-10
_SIDE_RESIDUAL_TOLERANCE = 1.0e-2
_PROFILE = 'task041_schur_speed_v2'
_NUMA_EVIDENCE_ENABLED = os.environ.get("TASK041_NUMA_EVIDENCE") == "1"
_F1_TRANSFER_DIAGNOSTICS = os.environ.get(
    "TASK041_F1_TRANSFER_DIAGNOSTICS"
) == "1"
_TRANSFER_DIAGNOSTIC_MAX_LOCAL_ROWS = 8
_TRANSFER_DIAGNOSTIC_MAX_GLOBAL_ROWS = 64
_NUMA_PROBE: mmap.mmap | None = None
_NUMA_PROBE_BYTES = 2 * 1024 * 1024
_NUMA_PAGE_BYTES = 4096


def _collective_require(
    comm: MPI.Intracomm,
    local: bool,
    message: str,
) -> None:
    passed = bool(comm.allreduce(bool(local), op=MPI.LAND))
    if not passed:
        raise AssertionError(message)


def _complex_pair(value: complex) -> list[float]:
    scalar = complex(value)
    return [float(scalar.real), float(scalar.imag)]


def _process_identity() -> dict[str, object]:
    pid = os.getpid()
    with open(f"/proc/{pid}/stat", encoding="utf-8") as stream:
        stat_line = stream.read().strip()
    _prefix, stat_tail = stat_line.rsplit(")", 1)
    stat_fields = stat_tail.split()
    if len(stat_fields) <= 19:
        raise ValueError("/proc/self/stat has no starttime field")
    affinity = sorted(os.sched_getaffinity(0))
    cpu_topology = []
    for cpu in affinity:
        cpu_root = Path(f"/sys/devices/system/cpu/cpu{cpu}")
        socket = int(
            (cpu_root / "topology/physical_package_id")
            .read_text(encoding="utf-8")
            .strip()
        )
        numa_nodes = sorted(
            int(path.name[4:])
            for path in cpu_root.glob("node[0-9]*")
        )
        cpu_topology.append({
            "os_cpu": int(cpu),
            "socket": socket,
            "numa_nodes": numa_nodes,
        })
    return {
        "pid": int(pid),
        "starttime_ticks": int(stat_fields[19]),
        "clock_ticks": int(os.sysconf("SC_CLK_TCK")),
        "sched_getaffinity": [int(cpu) for cpu in affinity],
        "cpu_topology": cpu_topology,
    }


def _collective_rank0_json(comm: MPI.Intracomm, payload: object) -> None:
    output_error = None
    if comm.rank == 0:
        try:
            print(json.dumps(payload, sort_keys=True, default=str), flush=True)
        except (OSError, TypeError, ValueError) as exc:
            output_error = f"{type(exc).__name__}: {exc}"
    output_ok = bool(comm.allreduce(output_error is None, op=MPI.LAND))
    if not output_ok:
        errors = comm.allgather(output_error)
        raise RuntimeError(
            "rank0 diagnostic output failed: " + repr(errors)
        )


def _collective_numa_memory_evidence(
    comm: MPI.Intracomm,
    stage: str,
    arrays: dict[str, object] | None = None,
) -> dict[str, object]:
    evidence = None
    local_error = None
    try:
        evidence = _numa_memory_evidence(stage, arrays)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        local_error = f"{type(exc).__name__}: {exc}"
        evidence = {
            "enabled": True,
            "stage": stage,
            "status": "not_observed",
        }
    all_ok = bool(comm.allreduce(local_error is None, op=MPI.LAND))
    if all_ok:
        evidence["collective_status"] = "measured"
    else:
        errors = comm.allgather(local_error)
        evidence["collective_status"] = "failed"
        evidence["rank_errors"] = [
            None if error is None else str(error) for error in errors
        ]
    return evidence


def _mempolicy_snapshot() -> dict[str, object]:
    libnuma = ctypes.CDLL("libnuma.so.1", use_errno=True)
    mode = ctypes.c_int()
    word_bits = ctypes.sizeof(ctypes.c_ulong) * 8
    maxnode = 1024
    words = (maxnode + word_bits - 1) // word_bits
    mask = (ctypes.c_ulong * words)()
    libnuma.get_mempolicy.argtypes = [
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    libnuma.get_mempolicy.restype = ctypes.c_int
    rc = int(libnuma.get_mempolicy(
        ctypes.byref(mode),
        mask,
        ctypes.c_ulong(maxnode),
        None,
        ctypes.c_int(0),
    ))
    if rc != 0:
        return {
            "status": "not_observed",
            "errno": int(ctypes.get_errno()),
            "error": "get_mempolicy_failed",
        }
    nodemask = [
        index
        for index in range(maxnode)
        if mask[index // word_bits] & (1 << (index % word_bits))
    ]
    return {
        "status": "measured",
        "mode": int(mode.value),
        "effective_nodemask": nodemask,
    }


def _mapping_line(address: int) -> dict[str, object]:
    mapping = None
    with open("/proc/self/maps", encoding="utf-8") as stream:
        for line in stream:
            bounds = line.split(maxsplit=1)[0].split("-", 1)
            start = int(bounds[0], 16)
            end = int(bounds[1], 16)
            if start <= address < end:
                mapping = {
                    "start": start,
                    "end": end,
                    "permissions": line.split()[1],
                    "raw": line.rstrip()[:512],
                }
                break
    if mapping is None:
        return {"status": "not_observed", "address": address}
    mapping["private"] = str(mapping["permissions"])[3:4] == "p"
    numa = None
    with open("/proc/self/numa_maps", encoding="utf-8") as stream:
        for line in stream:
            first = line.split(maxsplit=1)[0]
            if int(first, 16) == int(mapping["start"]):
                numa = line.rstrip()[:1024]
                break
    mapping["numa_maps"] = numa if numa is not None else "not_observed"
    return mapping


def _private_anon_samples(limit: int = 8) -> list[dict[str, object]]:
    mappings: dict[int, dict[str, object]] = {}
    with open("/proc/self/maps", encoding="utf-8") as stream:
        for line in stream:
            fields = line.split()
            bounds = fields[0].split("-", 1)
            start = int(bounds[0], 16)
            path = " ".join(fields[5:]) if len(fields) > 5 else ""
            mappings[start] = {
                "permissions": fields[1],
                "path": path,
                "private": fields[1][3] == "p",
            }
    candidates: list[dict[str, object]] = []
    with open("/proc/self/numa_maps", encoding="utf-8") as stream:
        for line in stream:
            fields = line.split()
            start = int(fields[0], 16)
            mapping = mappings.get(start)
            if mapping is None or not mapping["private"] or "file=" in line:
                continue
            if not any(field.startswith(("anon=", "heap", "stack")) for field in fields[1:]):
                continue
            nodes = {}
            for field in fields[1:]:
                if field.startswith("N") and "=" in field:
                    name, value = field.split("=", 1)
                    nodes[name] = int(value)
            anon_pages = next(
                (int(field.split("=", 1)[1]) for field in fields[1:]
                 if field.startswith("anon=")),
                None,
            )
            candidates.append({
                "mapping_start": start,
                "anon_pages": anon_pages,
                "nodes": nodes,
                "private": True,
                "path": mapping["path"],
                "raw": line.rstrip()[:1024],
            })
    candidates.sort(
        key=lambda item: (-int(item["anon_pages"] or 0), int(item["mapping_start"]))
    )
    return candidates[: int(limit)]


def _array_memory_mapping(name: str, value: object) -> dict[str, object]:
    array = value.getArray(readonly=True) if isinstance(value, PETSc.Vec) else np.asarray(value)
    address = int(array.__array_interface__["data"][0])
    mapping = _mapping_line(address)
    return {
        "object": name,
        "address": address,
        "bytes": int(array.nbytes),
        "pages": int((array.nbytes + _NUMA_PAGE_BYTES - 1) // _NUMA_PAGE_BYTES),
        "vma_aggregation": True,
        "private": bool(mapping.get("private", False)),
        "mapping": mapping,
    }


def _numa_memory_evidence(
    stage: str,
    arrays: dict[str, object] | None = None,
) -> dict[str, object]:
    global _NUMA_PROBE
    if not _NUMA_EVIDENCE_ENABLED:
        return {"enabled": False, "stage": stage}
    if _NUMA_PROBE is None:
        _NUMA_PROBE = mmap.mmap(
            -1,
            _NUMA_PROBE_BYTES,
            flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
            prot=mmap.PROT_READ | mmap.PROT_WRITE,
        )
        for offset in range(0, _NUMA_PROBE_BYTES, _NUMA_PAGE_BYTES):
            _NUMA_PROBE[offset] = 1
    address = ctypes.addressof(ctypes.c_char.from_buffer(_NUMA_PROBE))
    return {
        "enabled": True,
        "stage": stage,
        "pid": os.getpid(),
        "rank_identity": _process_identity(),
        "buffer": {
            "address": int(address),
            "bytes": _NUMA_PROBE_BYTES,
            "pages": _NUMA_PROBE_BYTES // _NUMA_PAGE_BYTES,
            "first_touch": True,
            "mapping": _mapping_line(address),
        },
        "task_policy": _mempolicy_snapshot(),
        "objects": [
            _array_memory_mapping(name, value)
            for name, value in (arrays or {}).items()
        ],
        "private_anon_heap_samples": _private_anon_samples(8),
    }


def _collective_array_unchanged(
    comm: MPI.Intracomm,
    vector: PETSc.Vec,
    before: np.ndarray,
    message: str,
) -> None:
    local = bool(
        np.array_equal(
            np.asarray(vector.getArray(readonly=True)),
            before,
        )
    )
    _collective_require(comm, local, message)


def _max_elapsed(comm: MPI.Intracomm, elapsed: float) -> float:
    return float(comm.allreduce(float(elapsed), op=MPI.MAX))


def _relative_difference(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.duplicate()
    try:
        left.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), right)
        numerator = float(difference.norm())
        denominator = float(right.norm())
        return numerator / denominator if denominator != 0.0 else numerator
    finally:
        difference.destroy()


def _explicit_side_residual(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
) -> dict[str, float | bool]:
    action = operator.createVecLeft()
    residual = rhs.duplicate()
    try:
        operator.mult(solution, action)
        rhs.copy(residual)
        residual.axpy(PETSc.ScalarType(-1.0), action)
        rhs_norm = float(rhs.norm())
        residual_norm = float(residual.norm())
        solution_norm = float(solution.norm())
        relative = (
            residual_norm / rhs_norm if rhs_norm != 0.0 else residual_norm
        )
        finite = bool(
            np.isfinite(rhs_norm)
            and np.isfinite(residual_norm)
            and np.isfinite(solution_norm)
            and np.isfinite(relative)
        )
        return {
            'rhs_norm': rhs_norm,
            'residual_norm': residual_norm,
            'solution_norm': solution_norm,
            'relative_residual': relative,
            'finite': finite,
        }
    finally:
        action.destroy()
        residual.destroy()


def _p4_audit_values(inverse) -> dict[str, object]:
    last_solve = inverse.diagnostics['p4_factor']['last_solve']
    return {
        'status': str(last_solve['status']),
        'a4_relative': float(last_solve['physical_relative_residual']),
        'backsolve_count': int(last_solve['backsolve_count']),
        'refinement_count': int(last_solve['refinement_count']),
    }


def _lifecycle_values(diagnostics: dict[str, object]) -> dict[str, object]:
    names = (
        'destroyed',
        'p4_factor_live',
        'p4_factor_created_count',
        'p4_factor_destroy_count',
        'nested_iterative_ksp_count',
        'nested_ksp_created_count',
        'nested_ksp_destroy_count',
    )
    return {name: diagnostics[name] for name in names if name in diagnostics}


def _compact_backend(result: dict[str, object]) -> dict[str, object]:
    names = (
        'backend',
        'setup_seconds',
        'q_seconds',
        'pc_seconds',
        'response_seconds',
        'timing_semantics',
        'ready_lifecycle',
        'released_lifecycle',
        'q_p4_audit',
        'pc_p4_audit',
        'response_p4_audit',
        'response_audit',
        'response_residual',
        'owner_facts',
        'input_unchanged',
        'rank_layout',
        'p6_v_identity',
        'p6_mpc_identity',
        'mapping',
    )
    return {name: result[name] for name in names}


def _mapping_summary(side_system) -> dict[str, object]:
    condensed = side_system.static_condensation.condensed
    original = np.asarray(
        condensed.trace_constraints.owned_active_original_dofs,
        dtype=np.int64,
    )
    return {
        'owned_active_original_dofs_count': int(original.size),
        'owned_active_original_dofs_sha256': hashlib.sha256(
            original.tobytes(),
        ).hexdigest(),
    }


def _rank_layout(side_system, transfer=None) -> dict[str, object]:
    comm = side_system.A.getComm().tompi4py()
    condensed = side_system.static_condensation.condensed
    mesh = side_system.local_mesh.mesh
    cell_map = mesh.topology.index_map(mesh.topology.dim)
    active_start, active_end = map(int, side_system.A.getOwnershipRange())
    remote_count = 0
    remote_ranks: set[int] = set()
    if transfer is not None:
        stops = np.asarray(
            [int(right) for _left, right in transfer.coarse_ranges],
            dtype=np.int64,
        )
        for record in transfer._records:
            coarse_global = np.asarray(
                record['coarse_global'],
                dtype=np.int64,
            )
            owners = np.searchsorted(stops, coarse_global, side='right')
            remote = owners[owners != comm.rank]
            remote_count += int(remote.size)
            remote_ranks.update(int(rank) for rank in remote)
    return {
        'rank': int(comm.rank),
        'owned_cells': int(cell_map.size_local),
        'ghost_cells': int(cell_map.num_ghosts),
        'active_range': [active_start, active_end],
        'owned_active_rows': int(condensed.owned_active_rows),
        'owned_port_rows': int(condensed.owned_appended_rows),
        'active_rows': int(condensed.active_rows),
        'port_rows': int(condensed.appended_rows),
        'mapping': _mapping_summary(side_system),
        'remote_candidate_dofs': int(remote_count),
        'remote_candidate_ranks': sorted(remote_ranks),
    }


def _attempt_summary(attempt: dict[str, object]) -> dict[str, object]:
    result = attempt.get("result")
    if result is None:
        return {
            "status": "exception",
            "exception_type": str(attempt["exception_type"]),
            "exception_message": str(attempt["exception_message"]),
        }
    return {
        "status": "returned",
        "resolved_rows": int(result[0].size),
        "global_defect": float(result[2]),
        "packet_rows": int(result[3]),
    }


def _resolved_value(attempt: dict[str, object], row_id: int) -> list[float] | None:
    result = attempt.get("result")
    if result is None:
        return None
    positions = np.flatnonzero(np.asarray(result[0], dtype=np.uint64) == int(row_id))
    if positions.size == 0:
        return None
    return _complex_pair(result[1][int(positions[0])])


def _entity_descriptor(element, basix_position: int) -> dict[str, int] | None:
    entity_dofs = getattr(element, "entity_dofs", None)
    if entity_dofs is None:
        return None
    for topological_dim, entities in enumerate(entity_dofs):
        for entity, dofs in enumerate(entities):
            if int(basix_position) in {int(value) for value in dofs}:
                return {
                    "topological_dim": int(topological_dim),
                    "entity": int(entity),
                    "basix_local_position": int(basix_position),
                }
    return None


def _mpc_descriptor(mpc, local_row: int) -> dict[str, object] | None:
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    row = int(local_row)
    if row < 0 or row + 1 >= offsets.size:
        return None
    start = int(offsets[row])
    stop = int(offsets[row + 1])
    masters = np.asarray(mpc.masters.links(row), dtype=np.int64)
    row_coefficients = coefficients[start:stop]
    if masters.size != row_coefficients.size:
        return None
    return {
        "local_row": row,
        "masters": [int(value) for value in masters],
        "phases": [_complex_pair(value) for value in row_coefficients],
    }


def _coarse_work_snapshot(transfer, owner_ranges) -> dict[str, object]:
    array = np.asarray(
        transfer._coarse_work.x.array,
        dtype=np.complex128,
    )
    local_ids = np.arange(array.size, dtype=np.int32)
    index_map = transfer.coarse_floquet.mpc.function_space.dofmap.index_map
    try:
        global_ids = np.asarray(index_map.local_to_global(local_ids), dtype=np.int64)
    except (AttributeError, TypeError, ValueError):
        global_ids = None
    owner_stops = np.asarray(
        [int(right) for _left, right in owner_ranges],
        dtype=np.int64,
    )
    owners = None if global_ids is None else np.searchsorted(
        owner_stops, global_ids, side="right"
    ).astype(np.int64)
    return {
        "local_ids": [int(value) for value in local_ids],
        "global_ids": (
            None if global_ids is None
            else [int(value) for value in global_ids]
        ),
        "owner_ranks": (
            None if owners is None
            else [int(value) for value in owners]
        ),
        "owner_ranges": [
            [int(left), int(right)] for left, right in owner_ranges
        ],
        "values": [_complex_pair(value) for value in array],
        "local_sha256": hashlib.sha256(
            np.ascontiguousarray(array).tobytes()
        ).hexdigest(),
        "memory_mapping": _array_memory_mapping("coarse_work", array),
        "vma_note": "full local owned+ghost coarse_work array; VMA aggregation applies",
    }


def _diagnostic_local_worst_rows(
    ids: np.ndarray,
    values: np.ndarray,
    source_ranks: np.ndarray,
    owner_rank: int,
) -> list[dict[str, object]]:
    local_top: list[dict[str, object]] = []
    cursor = 0
    while cursor < int(ids.size):
        end = cursor + 1
        while end < int(ids.size) and ids[end] == ids[cursor]:
            end += 1
        group_sources = source_ranks[cursor:end]
        preferred = np.flatnonzero(group_sources == int(owner_rank))
        if preferred.size:
            reference_position = cursor + int(preferred[0])
            reference = complex(values[reference_position])
            defect = float(np.max(np.abs(values[cursor:end] - reference)))
            canonical_source = int(source_ranks[reference_position])
        else:
            reference = 0.0j
            defect = float("inf")
            canonical_source = None
        local_top.append({
            "row_id": int(ids[cursor]),
            "defect": defect,
            "candidate_count": int(end - cursor),
            "canonical_source_rank": canonical_source,
            "canonical_value": _complex_pair(reference),
        })
        local_top.sort(
            key=lambda item: (
                -float(item["defect"])
                if np.isfinite(float(item["defect"]))
                else float("-inf"),
                int(item["row_id"]),
            )
        )
        del local_top[_TRANSFER_DIAGNOSTIC_MAX_LOCAL_ROWS:]
        cursor = end
    return local_top


def _transfer_diagnostic_callback(
    transfer,
    *,
    ids: np.ndarray,
    values: np.ndarray,
    source_ranks: np.ndarray,
    owner_rank: int,
    owner_ranges,
    coarse_owner_ranges,
    attempts: dict[str, dict[str, object]],
    emitted_ids: np.ndarray,
    emitted_values: np.ndarray,
    source: PETSc.Vec,
) -> dict[str, object]:
    comm = transfer.comm
    local_error: str | None = None
    coarse_work_snapshot = None
    p4_source_snapshot = None
    try:
        coarse_work_snapshot = _coarse_work_snapshot(
            transfer, coarse_owner_ranges
        )
        p4_source_snapshot = _vector_diagnostic_snapshot(
            "p4_source", source
        )
        local_top = _diagnostic_local_worst_rows(
            ids, values, source_ranks, owner_rank
        )
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
        local_top = []
        local_error = f"{type(exc).__name__}: {exc}"
    diagnostic_state = getattr(transfer, "_diagnostic_context", None)
    if diagnostic_state is not None:
        diagnostic_state["coarse_work"] = coarse_work_snapshot
        diagnostic_state["p4_source"] = p4_source_snapshot
        diagnostic_state["snapshot_status"] = (
            "captured" if local_error is None else "not_observed"
        )
    if not bool(comm.allreduce(local_error is None, op=MPI.LAND)):
        raise RuntimeError("diagnostic local row preparation failed")
    gathered_top = comm.allgather(local_top)
    candidates = [item for rank_items in gathered_top for item in rank_items]
    candidates.sort(
        key=lambda item: (
            -float(item["defect"])
            if np.isfinite(float(item["defect"]))
            else float("-inf"),
            int(item["row_id"]),
        )
    )
    selected_ids: list[int] = []
    for item in candidates:
        row_id = int(item["row_id"])
        if row_id not in selected_ids:
            selected_ids.append(row_id)
        if len(selected_ids) >= _TRANSFER_DIAGNOSTIC_MAX_GLOBAL_ROWS:
            break

    received_candidates: list[dict[str, object]] = []
    selected_set = set(selected_ids)
    for index, row_id in enumerate(ids):
        if int(row_id) in selected_set:
            received_candidates.append({
                "row_id": int(row_id),
                "source_rank": int(source_ranks[index]),
                "value": _complex_pair(values[index]),
            })

    emitted_candidates: list[dict[str, object]] = []
    emitted_offset = 0
    for record_index, record in enumerate(transfer._records):
        record_ids = np.asarray(record["fine_global"], dtype=np.uint64)
        record_stop = emitted_offset + int(record_ids.size)
        if record_stop > int(emitted_ids.size) or record_stop > int(emitted_values.size):
            raise ValueError("emitted candidate packet is shorter than records")
        if not np.array_equal(emitted_ids[emitted_offset:record_stop], record_ids):
            raise ValueError("emitted candidate ids do not match record order")
        for position, row_id in enumerate(record_ids):
            if int(row_id) in selected_set:
                emitted_index = emitted_offset + int(position)
                emitted_candidates.append({
                    "row_id": int(row_id),
                    "source_rank": int(comm.rank),
                    "record_index": int(record_index),
                    "record_position": int(position),
                    "emitted_index": int(emitted_index),
                    "value": _complex_pair(emitted_values[emitted_index]),
                })
        emitted_offset = record_stop
    if emitted_offset != int(emitted_ids.size) or emitted_offset != int(emitted_values.size):
        raise ValueError("emitted candidate packet has unexpected record length")

    topology = transfer.mesh.topology
    topology.create_entity_permutations()
    permutation_info = np.asarray(
        topology.get_cell_permutation_info(),
        dtype=np.uint32,
    )
    cell_map = topology.index_map(topology.dim)
    coarse_mpc = transfer.coarse_floquet.mpc
    local_provenance: list[dict[str, object]] = []
    owner_stops = np.asarray(
        [int(right) for _left, right in owner_ranges],
        dtype=np.int64,
    )
    emitted_offset = 0
    for cell, record in enumerate(transfer._records):
        local_values = np.asarray(
            transfer._coarse_work.x.array[record["coarse_local"]],
            dtype=np.complex128,
        )
        for position, row_id in enumerate(record["fine_global"]):
            if int(row_id) not in selected_set:
                continue
            cell_global = np.asarray(
                cell_map.local_to_global(np.asarray([cell], dtype=np.int32))
            )
            local_dof = int(record["fine_local"][position])
            emitted_index = emitted_offset + int(position)
            row_owner = int(
                np.searchsorted(owner_stops, int(row_id), side="right")
            )
            local_provenance.append({
                "row_id": int(row_id),
                "source_rank": int(comm.rank),
                "owner_rank": row_owner,
                "ghost": row_owner != int(comm.rank),
                "cell_local": int(cell),
                "cell_global": int(cell_global[0]),
                "cell_permutation_info": int(permutation_info[cell]),
                "basix_local_position": int(position),
                "rank_local_storage_dof": local_dof,
                "entity": _entity_descriptor(
                    transfer.fine_space.element.basix_element,
                    int(position),
                ),
                "candidate_value": _complex_pair(
                    emitted_values[emitted_index]
                ),
                "recomputed_row_dot": _complex_pair(
                    record["matrix"][position, :] @ local_values
                ),
                "T_row": [
                    _complex_pair(value)
                    for value in record["matrix"][position, :]
                ],
                "coarse_global_ids": [
                    int(value) for value in record["coarse_global"]
                ],
                "coarse_local_ids": [
                    int(value) for value in record["coarse_local"]
                ],
                "coarse_values": [_complex_pair(value) for value in local_values],
                "coarse_mpc_rows": [
                    _mpc_descriptor(coarse_mpc, int(local_row))
                    for local_row in record["coarse_local"]
                ],
            })
        emitted_offset += int(np.asarray(record["fine_global"]).size)

    def _packet_digest(array: np.ndarray) -> str:
        return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()

    canonical = {}
    for row_id in selected_ids:
        canonical[str(row_id)] = {
            "legacy": _resolved_value(attempts["legacy"], row_id),
            "batched": _resolved_value(attempts["batched"], row_id),
        }
    return {
        "packet_rows": int(ids.size),
        "packet_sha256": ":".join((
            _packet_digest(ids),
            _packet_digest(values),
            _packet_digest(source_ranks),
        )),
        "local_worst_rows": local_top,
        "selected_row_ids": selected_ids,
        "canonical_selected": canonical,
        "received_candidates": received_candidates,
        "emitted_candidates": emitted_candidates,
        "local_provenance": local_provenance,
        "coarse_work": coarse_work_snapshot,
        "p4_source": p4_source_snapshot,
        "attempts": {
            "legacy": _attempt_summary(attempts["legacy"]),
            "batched": _attempt_summary(attempts["batched"]),
        },
    }

def _vector_memory_summary(name: str, vector: PETSc.Vec) -> dict[str, object]:
    array = np.ascontiguousarray(vector.getArray(readonly=True))
    return {
        "object": name,
        "address": int(array.__array_interface__["data"][0]),
        "bytes": int(array.nbytes),
        "local_size": int(array.size),
        "local_norm": float(np.linalg.norm(array)),
        "finite": bool(np.all(np.isfinite(array))),
        "local_sha256": hashlib.sha256(array.tobytes()).hexdigest(),
    }


def _vector_diagnostic_snapshot(name: str, vector: PETSc.Vec) -> dict[str, object]:
    array = np.ascontiguousarray(
        vector.getArray(readonly=True),
        dtype=np.complex128,
    )
    return {
        "object": name,
        "ownership_range": [int(value) for value in vector.getOwnershipRange()],
        "global_size": int(vector.getSize()),
        "local_size": int(vector.getLocalSize()),
        "values": [_complex_pair(value) for value in array],
        "local_norm": float(np.linalg.norm(array)),
        "local_sha256": hashlib.sha256(array.tobytes()).hexdigest(),
        "finite": bool(np.all(np.isfinite(array))),
        "memory_mapping": _array_memory_mapping(name, vector),
    }


def _run_backend(
    side_system,
    source: PETSc.Vec,
    rhs: PETSc.Vec,
    full_source: PETSc.Vec | None,
    backend: str,
    side: str,
    *,
    diagnostic_only: bool = False,
    support_policy: str = "entity_closure",
) -> dict[str, object]:
    comm = side_system.A.getComm().tompi4py()
    operator = side_system.A
    inverse = None
    q_output = None
    pc_output = None
    response_output = None
    q_p4_audit = None
    numa_evidence: list[dict[str, object]] = []
    q_input_summary = None
    q_output_summary = None
    local_full_source = full_source
    stage = 'setup'
    try:
        setup_started = perf_counter()
        inverse = build_side_balanced_inverse(
            side_system,
            detailed_timing=True,
            performance_profile=_PROFILE,
            p4_inverse_backend=backend,
            support_policy=support_policy,
        )
        setup_seconds = _max_elapsed(comm, perf_counter() - setup_started)
        ready_lifecycle = _lifecycle_values(inverse.diagnostics)
        _collective_require(
            comm,
            inverse._side_system is side_system,
            f'{backend}: side system identity changed',
        )
        p6_v_identity = inverse._full_action.V is side_system.V
        p6_mpc_identity = (
            inverse._full_action.floquet_data.mpc
            is side_system.floquet_data.mpc
        )
        _collective_require(
            comm,
            p6_v_identity and p6_mpc_identity,
            f'{backend}: p6 V/MPC is not borrowed from the side system',
        )
        _collective_require(
            comm,
            inverse._owner_transfer.audit["support_policy"] == support_policy,
            f'{backend}: transfer support policy was not forwarded',
        )
        _collective_require(
            comm,
            inverse._condensed
            is side_system.static_condensation.condensed,
            f'{backend}: condensed system is not borrowed from the side system',
        )
        _collective_require(
            comm,
            inverse._full_action.local_mesh is side_system.local_mesh,
            f'{backend}: full action mesh is not borrowed from the side system',
        )
        _collective_require(
            comm,
            bool(inverse._ksp.getInitialGuessNonzero()) is False,
            f'{backend}: KSP initial guess is enabled',
        )
        if local_full_source is None:
            local_full_source = inverse._full_action.matrix.createVecRight()
            inject_active_residual_to_full_p6(
                side_system.static_condensation.condensed,
                source,
                local_full_source,
            )
        _collective_require(
            comm,
            local_full_source.getSize()
            == inverse._full_action.matrix.getSize()[1]
            and tuple(local_full_source.getOwnershipRange())
            == tuple(inverse._full_action.matrix.getOwnershipRange()),
            f'{backend}: full p6 source ownership does not match',
        )
        if _NUMA_EVIDENCE_ENABLED:
            transfer = inverse._owner_transfer
            p4_ready_evidence = _collective_numa_memory_evidence(
                comm,
                "p4_ready",
                {
                    "p6_full_source": local_full_source,
                    "transfer_coarse_work": transfer._coarse_work.x.array,
                    "transfer_fine_work": transfer._fine_work.x.array,
                },
            )
            numa_evidence.append(p4_ready_evidence)
            ready_layout = _rank_layout(side_system, transfer)
            ready_by_rank = comm.gather(
                {
                    "rank": int(comm.rank),
                    "identity": p4_ready_evidence.get("rank_identity"),
                    "layout": ready_layout,
                    "p4_ready_status": p4_ready_evidence.get(
                        "collective_status", "not_observed"
                    ),
                },
                root=0,
            )
            _collective_rank0_json(
                comm,
                {
                    "schema": "task041.h1e.mpi8.p4_ready.v1",
                    "ranks": ready_by_rank,
                },
            )
            _collective_require(
                comm,
                p4_ready_evidence.get("collective_status") == "measured",
                f"{backend}: p4-ready NUMA evidence failed",
            )
            q_input_summary = comm.allgather(
                _vector_memory_summary("p6_full_source", local_full_source)
            )

        full_source_before_q = np.asarray(
            local_full_source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        stage = 'q'
        q_started = perf_counter()
        if diagnostic_only:
            with inverse._owner_transfer.diagnostic_context(
                lambda **payload: _transfer_diagnostic_callback(**payload)
            ):
                q_output = inverse._apply_q_callback(local_full_source)
        else:
            q_output = inverse._apply_q_callback(local_full_source)
        q_seconds = _max_elapsed(comm, perf_counter() - q_started)
        _collective_array_unchanged(
            comm,
            local_full_source,
            full_source_before_q,
            f'{backend}: Q modified full p6 source',
        )
        q_p4_audit = _p4_audit_values(inverse)
        if _NUMA_EVIDENCE_ENABLED:
            first_q_evidence = _collective_numa_memory_evidence(
                comm,
                "first_q_response",
                {
                    "q_output": q_output,
                    "p6_full_source": local_full_source,
                },
            )
            numa_evidence.append(first_q_evidence)
            _collective_require(
                comm,
                first_q_evidence.get("collective_status") == "measured",
                f"{backend}: first-Q NUMA evidence failed",
            )
            q_output_summary = comm.allgather(
                _vector_memory_summary("q_output", q_output)
            )
        if diagnostic_only:
            transfer = inverse._owner_transfer
            diagnostic_state = dict(transfer.last_diagnostic)
            diagnostic_state["p4_audit"] = q_p4_audit
            transfer_diagnostic = comm.gather(
                diagnostic_state,
                root=0,
            )
            rank_layout = comm.allgather(_rank_layout(side_system, transfer))
            stage = 'diagnostic_release'
            inverse.destroy()
            released = inverse.diagnostics
            released_lifecycle = _lifecycle_values(released)
            inverse = None
            if q_output is not None:
                q_output.destroy()
                q_output = None
            if local_full_source is not None and full_source is None:
                local_full_source.destroy()
                local_full_source = None
            return {
                'backend': backend,
                'diagnostic_only': True,
                'q_status': 'completed',
                'setup_seconds': setup_seconds,
                'q_seconds': q_seconds,
                'pc_seconds': None,
                'response_seconds': None,
                'timing_semantics': (
                    'setup and Q values are per-action MPI.MAX across ranks; '
                    'they are not service or parent wall-clock intervals'
                ),
                'ready_lifecycle': ready_lifecycle,
                'released_lifecycle': released_lifecycle,
                'q_p4_audit': q_p4_audit,
                'transfer_diagnostic': transfer_diagnostic,
                'q_input_summary': q_input_summary,
                'q_output_summary': q_output_summary,
                'numa_evidence': numa_evidence,
                'rank_layout': rank_layout,
                'p6_v_identity': p6_v_identity,
                'p6_mpc_identity': p6_mpc_identity,
                'mapping': _mapping_summary(side_system),
            }

        full_source_before_pc = np.asarray(
            local_full_source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        source_before_pc = np.asarray(
            source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        pc_output = operator.createVecLeft()
        pc_output.set(0.0)
        stage = 'pc'
        pc_started = perf_counter()
        inverse._apply_balanced_pc(source, pc_output)
        pc_seconds = _max_elapsed(comm, perf_counter() - pc_started)
        _collective_array_unchanged(
            comm,
            local_full_source,
            full_source_before_pc,
            f'{backend}: PC modified full p6 source',
        )
        _collective_array_unchanged(
            comm,
            source,
            source_before_pc,
            f'{backend}: PC modified active source',
        )
        pc_p4_audit = _p4_audit_values(inverse)

        rhs_before_response = np.asarray(
            rhs.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        full_source_before_response = np.asarray(
            local_full_source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        response_output = operator.createVecLeft()
        response_output.set(0.0)
        stage = 'response'
        response_started = perf_counter()
        inverse.apply(rhs, response_output)
        response_seconds = _max_elapsed(
            comm,
            perf_counter() - response_started,
        )
        response_audit = dict(inverse.diagnostics['last_apply'])
        response_p4_audit = _p4_audit_values(inverse)
        response_residual = _explicit_side_residual(
            operator,
            rhs,
            response_output,
        )
        _collective_array_unchanged(
            comm,
            rhs,
            rhs_before_response,
            f'{backend}: response modified RHS',
        )
        _collective_array_unchanged(
            comm,
            local_full_source,
            full_source_before_response,
            f'{backend}: response modified full p6 source',
        )
        transfer = inverse._owner_transfer
        owner_facts = dict(transfer.last_apply_facts)
        rank_layout = comm.allgather(_rank_layout(side_system, transfer))

        stage = 'release'
        inverse.destroy()
        released = inverse.diagnostics
        released_lifecycle = _lifecycle_values(released)
        _collective_require(
            comm,
            released['destroyed'] is True
            and released['p4_factor_live'] == 0
            and released['nested_iterative_ksp_count'] == 0,
            f'{backend}: factor/KSP cleanup was incomplete',
        )
        inverse = None
        return {
            'backend': backend,
            'diagnostic_only': False,
            'setup_seconds': setup_seconds,
            'q_seconds': q_seconds,
            'pc_seconds': pc_seconds,
            'response_seconds': response_seconds,
            'timing_semantics': (
                'setup and action values are per-action MPI.MAX across ranks; '
                'they are not service or parent wall-clock intervals'
            ),
            'ready_lifecycle': ready_lifecycle,
            'released_lifecycle': released_lifecycle,
            'q_p4_audit': q_p4_audit,
            'pc_p4_audit': pc_p4_audit,
            'response_p4_audit': response_p4_audit,
            'response_audit': dict(response_audit),
            'response_residual': response_residual,
            'owner_facts': owner_facts,
            'input_unchanged': True,
            'rank_layout': rank_layout,
            'p6_v_identity': p6_v_identity,
            'p6_mpc_identity': p6_mpc_identity,
            'mapping': _mapping_summary(side_system),
            'q_input_summary': q_input_summary,
            'q_output_summary': q_output_summary,
            'numa_evidence': numa_evidence,
            'full_source': local_full_source,
            'q_output': q_output,
            'pc_output': pc_output,
            'response_output': response_output,
        }
    except BaseException as exc:
        rank_failure = {
            'rank': int(comm.rank),
            'side': side,
            'backend': backend,
            'stage': stage,
            'exception_type': type(exc).__name__,
            'exception': str(exc),
        }
        rank_failure['q_status'] = (
            'completed' if q_output is not None else 'not_completed'
        )
        rank_failure['numa_evidence'] = numa_evidence
        if inverse is not None:
            diagnostics = inverse.diagnostics
            if 'p4_factor' in diagnostics:
                rank_failure['p4_last_solve'] = dict(
                    diagnostics['p4_factor']['last_solve']
                )
            if 'last_apply' in diagnostics:
                rank_failure['last_apply'] = dict(diagnostics['last_apply'])
            transfer_diagnostic = dict(
                inverse._owner_transfer.last_diagnostic
            )
            if diagnostic_only:
                try:
                    transfer_diagnostic['p4_audit'] = _p4_audit_values(
                        inverse
                    )
                except (KeyError, TypeError, ValueError):
                    transfer_diagnostic['p4_audit'] = {
                        'status': 'not_observed',
                    }
            rank_failure['transfer_diagnostic'] = transfer_diagnostic
        rank_failures = (
            comm.gather(rank_failure, root=0)
            if diagnostic_only
            else None
        )
        if comm.rank == 0:
            failure = dict(rank_failure)
            failure['schema'] = 'task041.h1e.mpi8.side_backend_failure.v1'
            if diagnostic_only:
                failure['rank_failures'] = rank_failures
            failure['q_status'] = rank_failure['q_status']
            failure['q_input_summary'] = q_input_summary
            failure['q_output_summary'] = q_output_summary
            failure['numa_evidence'] = numa_evidence
            print(json.dumps(failure, sort_keys=True, default=str), flush=True)
        if inverse is not None:
            inverse.destroy()
        if local_full_source is not None and full_source is None:
            local_full_source.destroy()
        for vector in (q_output, pc_output, response_output):
            if vector is not None:
                vector.destroy()
        raise


def test_task041_h1e_mpi8_side_inverse_old_new_q_pc_and_apply() -> None:
    '''Run one bottom-to-top MPI8 paired side comparison only.'''

    comm = MPI.COMM_WORLD
    cfg = replace(
        _fixture_config(6, condensed=True),
        mesh_axis_cell_counts=(4, 2, 2),
    )
    if _NUMA_EVIDENCE_ENABLED:
        startup_evidence = _collective_numa_memory_evidence(
            comm,
            'rank_start',
        )
        startup_by_rank = comm.gather(startup_evidence, root=0)
        _collective_rank0_json(
            comm,
            {
                'schema': 'task041.h1e.mpi8.numa_start.v1',
                'ranks': startup_by_rank,
            },
        )
        _collective_require(
            comm,
            startup_evidence.get('collective_status') == 'measured',
            'rank-start NUMA evidence failed',
        )
    side_records: list[dict[str, object]] = []

    for side in ('bottom', 'top'):
        mesh = None
        side_system = None
        source = None
        rhs = None
        full_source = None
        old = None
        new = None
        try:
            mesh = build_hybrid_local_mesh(
                cfg,
                side,
                bottom_interface_z_nm=0.5,
                top_interface_z_nm=0.5,
                comm=comm,
            )
            side_system = assemble_hybrid_local_dtn_action_system(
                cfg,
                side,
                local_mesh_override=mesh,
                comm=comm,
            )
            preflight_layout = comm.allgather(_rank_layout(side_system))
            global_cells_preflight = sum(
                int(item['owned_cells']) for item in preflight_layout
            )
            every_rank_owns_cells = all(
                int(item['owned_cells']) > 0 for item in preflight_layout
            )
            partition_ok = (
                global_cells_preflight == 8 and every_rank_owns_cells
            )
            if not partition_ok and comm.rank == 0:
                print(
                    json.dumps(
                        {
                            'schema': (
                                'task041.h1e.mpi8.partition_failure.v1'
                            ),
                            'side': side,
                            'mpi_size': int(comm.size),
                            'global_owned_cells': global_cells_preflight,
                            'every_rank_owns_cells': every_rank_owns_cells,
                            'rank_layout_preflight': preflight_layout,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            _collective_require(
                comm,
                partition_ok,
                f'{side}: MPI8 partition must own eight cells with every rank nonzero',
            )
            operator = side_system.A
            source = operator.createVecRight()
            rhs = operator.createVecLeft()
            _fill_active(source, 1.25)
            operator.mult(source, rhs)
            rhs_norm = float(rhs.norm())
            _collective_require(
                comm,
                np.isfinite(rhs_norm) and rhs_norm > 0.0,
                f'{side}: fixed nonzero RHS norm is invalid',
            )
            source_before = np.asarray(
                source.getArray(readonly=True),
                dtype=np.complex128,
            ).copy()
            rhs_before = np.asarray(
                rhs.getArray(readonly=True),
                dtype=np.complex128,
            ).copy()
            b_before = np.asarray(
                side_system.b.getArray(readonly=True),
                dtype=np.complex128,
            ).copy()
            if _F1_TRANSFER_DIAGNOSTICS:
                f1_result = _run_backend(
                   side_system,
                   source,
                   rhs,
                   None,
                   'full',
                   side,
                   diagnostic_only=True,
                    support_policy="entity_closure",
               )
                if comm.rank == 0:
                    print(
                        json.dumps(
                            {
                                'schema': 'task041.h1e.mpi8.f1_only.v1',
                                'side': side,
                                'result': f1_result,
                            },
                            sort_keys=True,
                            default=str,
                        ),
                        flush=True,
                    )
                return

            old = _run_backend(
                side_system,
                source,
                rhs,
                None,
                'full',
                side,
            )
            full_source = old['full_source']
            borrowed_after_old = _explicit_side_residual(
                operator,
                rhs,
                source,
            )
            new = _run_backend(
                side_system,
                source,
                rhs,
                full_source,
                'cell_condensed',
                side,
            )
            borrowed_after_new = _explicit_side_residual(
                operator,
                rhs,
                source,
            )

            q_relative = _relative_difference(
                new['q_output'],
                old['q_output'],
            )
            pc_relative = _relative_difference(
                new['pc_output'],
                old['pc_output'],
            )
            e_x = _relative_difference(
                new['response_output'],
                old['response_output'],
            )
            response_delta = new['response_output'].duplicate()
            delta_action = operator.createVecLeft()
            try:
                new['response_output'].copy(response_delta)
                response_delta.axpy(
                    PETSc.ScalarType(-1.0),
                    old['response_output'],
                )
                operator.mult(response_delta, delta_action)
                delta_action_norm = float(delta_action.norm())
                rhs_norm = float(rhs.norm())
                e_a = (
                    delta_action_norm / rhs_norm
                    if rhs_norm != 0.0
                    else delta_action_norm
                )
            finally:
                response_delta.destroy()
                delta_action.destroy()

            old_layout = old['rank_layout']
            new_layout = new['rank_layout']
            global_cells = global_cells_preflight
            global_active_rows = sum(
                int(item['owned_active_rows']) for item in old_layout
            )
            global_port_rows = sum(
                int(item['owned_port_rows']) for item in old_layout
            )
            remote_candidate_dofs = sum(
                int(item['remote_candidate_dofs']) for item in old_layout
            )
            old_rank_remote = sum(
                bool(item['remote_candidate_ranks']) for item in old_layout
            )
            new_rank_remote = sum(
                bool(item['remote_candidate_ranks']) for item in new_layout
            )
            input_unchanged_local = (
                np.array_equal(
                    source.getArray(readonly=True),
                    source_before,
                )
                and np.array_equal(
                    rhs.getArray(readonly=True),
                    rhs_before,
                )
                and np.array_equal(
                    side_system.b.getArray(readonly=True),
                    b_before,
                )
                and old['input_unchanged']
                and new['input_unchanged']
            )
            input_unchanged = bool(
                comm.allreduce(input_unchanged_local, op=MPI.LAND)
            )
            same_layout_local = (
                old_layout == new_layout
                and old['p6_v_identity']
                and old['p6_mpc_identity']
                and new['p6_v_identity']
                and new['p6_mpc_identity']
            )
            same_layout = bool(
                comm.allreduce(same_layout_local, op=MPI.LAND)
            )
            same_mapping_local = (
                old['mapping'] == new['mapping']
                and all(
                    item_old['mapping'] == item_new['mapping']
                    for item_old, item_new in zip(
                        old_layout,
                        new_layout,
                        strict=True,
                    )
                )
            )
            same_mapping = bool(
                comm.allreduce(same_mapping_local, op=MPI.LAND)
            )
            side_record = {
                'schema': 'task041.h1e.mpi8.side_backend_compare.v1',
                'diagnostic_before_assertions': True,
                'side': side,
                'mpi_size': int(comm.size),
                'mesh_axis_cell_counts': [4, 2, 2],
                'global_owned_cells': global_cells,
                'global_owned_active_rows': global_active_rows,
                'global_owned_port_rows': global_port_rows,
                'remote_candidate_dofs': remote_candidate_dofs,
                'ranks_with_remote_candidates_old': old_rank_remote,
                'ranks_with_remote_candidates_new': new_rank_remote,
                'rank_layout_preflight': preflight_layout,
                'rank_layout_old': old_layout,
                'rank_layout_new': new_layout,
                'profile': _PROFILE,
                'backend_sequence': 'full_destroyed_then_cell_condensed',
                'same_p6_v_mpc_layout': same_layout,
                'same_owned_active_mapping': same_mapping,
                'input_unchanged': input_unchanged,
                'rhs_norm': rhs_norm,
                'borrowed_A_after_old_destroy': borrowed_after_old,
                'borrowed_A_after_new_destroy': borrowed_after_new,
                'q_relative': float(q_relative),
                'q_tolerance': _Q_TOLERANCE,
                'pc_relative': float(pc_relative),
                'pc_tolerance': _PC_TOLERANCE,
                'e_x': float(e_x),
                'e_A': float(e_a),
                'e_tolerance': 1.0e-8,
                'old': _compact_backend(old),
                'new': _compact_backend(new),
            }
            side_records.append(side_record)
            if comm.rank == 0:
                print(
                    json.dumps(side_record, sort_keys=True, default=str),
                    flush=True,
                )

            _collective_require(
                comm,
                global_cells == 8,
                f'{side}: expected exactly 8 owned cells globally',
            )
            _collective_require(
                comm,
                every_rank_owns_cells,
                f'{side}: at least one MPI rank owns no cell',
            )
            _collective_require(
                comm,
                global_active_rows == old_layout[0]['active_rows'],
                f'{side}: active ownership does not close globally',
            )
            _collective_require(
                comm,
                global_port_rows == old_layout[0]['port_rows'],
                f'{side}: port ownership does not close globally',
            )
            _collective_require(
                comm,
                remote_candidate_dofs > 0
                and old_rank_remote > 0
                and new_rank_remote > 0,
                f'{side}: no cross-rank owner evidence was observed',
            )
            _collective_require(
                comm,
                same_layout and input_unchanged,
                f'{side}: borrowed layout or input changed',
            )
            _collective_require(
                comm,
                same_mapping,
                f'{side}: owned active original mapping changed',
            )
            _collective_require(
                comm,
                np.isfinite(rhs_norm) and rhs_norm > 0.0,
                f'{side}: fixed RHS norm is not positive',
            )
            _collective_require(
                comm,
                np.isfinite(q_relative) and q_relative <= _Q_TOLERANCE,
                f'{side}: Q comparison gate failed',
            )
            _collective_require(
                comm,
                np.isfinite(pc_relative) and pc_relative <= _PC_TOLERANCE,
                f'{side}: PC comparison gate failed',
            )
            for backend, borrowed in (
                (old, borrowed_after_old),
                (new, borrowed_after_new),
            ):
                _collective_require(
                    comm,
                    bool(borrowed['finite'])
                    and borrowed['relative_residual'] <= 1.0e-12,
                    f'{side}/{backend["backend"]}: borrowed A changed',
                )
            _collective_require(
                comm,
                np.isfinite(e_x)
                and np.isfinite(e_a)
                and e_x <= 1.0e-8
                and e_a <= 1.0e-8,
                f'{side}: e_x/e_A diagnostic gate failed',
            )
            for backend in (old, new):
                for audit_name in (
                    'q_p4_audit',
                    'pc_p4_audit',
                    'response_p4_audit',
                ):
                    audit = backend[audit_name]
                    _collective_require(
                        comm,
                        audit['status'] == 'passed'
                        and np.isfinite(audit['a4_relative'])
                        and audit['a4_relative'] <= _A4_TOLERANCE
                        and 1 <= audit['backsolve_count'] <= 3
                        and audit['refinement_count'] <= 2,
                        f'{side}/{backend["backend"]}/{audit_name}: '
                        'p4 audit gate failed',
                    )
                response = backend['response_residual']
                _collective_require(
                    comm,
                    bool(response['finite'])
                    and response['relative_residual']
                    <= _SIDE_RESIDUAL_TOLERANCE,
                    f'{side}/{backend["backend"]}: side residual gate failed',
                )
                response_audit = backend['response_audit']
                counts = response_audit['counts']
                operation_seconds = response_audit['operation_seconds']
                _collective_require(
                    comm,
                    response_audit['status'] == 'KSP_CONVERGED'
                    and isinstance(response_audit['reason'], int)
                    and response_audit['reason'] > 0
                    and response_audit['ksp_positive'] is True
                    and response_audit[
                        'explicit_true_target_reached'
                    ] is True
                    and isinstance(counts, dict)
                    and 'delta' in counts
                    and 'cumulative' in counts
                    and isinstance(operation_seconds, dict),
                    f'{side}/{backend["backend"]}: KSP audit is incomplete',
                )
                ready = backend['ready_lifecycle']
                released = backend['released_lifecycle']
                lifecycle_names = (
                    'destroyed',
                    'p4_factor_live',
                    'p4_factor_created_count',
                    'p4_factor_destroy_count',
                    'nested_iterative_ksp_count',
                    'nested_ksp_created_count',
                    'nested_ksp_destroy_count',
                )
                _collective_require(
                    comm,
                    all(name in ready for name in lifecycle_names)
                    and all(name in released for name in lifecycle_names)
                    and ready['destroyed'] is False
                    and ready['p4_factor_live'] == 1
                    and ready['p4_factor_created_count'] == 1
                    and ready['p4_factor_destroy_count'] == 0
                    and ready['nested_iterative_ksp_count'] == 1
                    and ready['nested_ksp_created_count'] == 1
                    and ready['nested_ksp_destroy_count'] == 0
                    and released['destroyed'] is True
                    and released['p4_factor_live'] == 0
                    and released['nested_iterative_ksp_count'] == 0
                    and released['p4_factor_created_count'] == 1
                    and released['p4_factor_destroy_count'] == 1
                    and released['nested_ksp_created_count'] == 1
                    and released['nested_ksp_destroy_count'] == 1,
                   f'{side}/{backend["backend"]}: lifecycle evidence incomplete',
               )
        finally:
            for backend in (new, old):
                if backend is not None:
                    for name in ('q_output', 'pc_output', 'response_output'):
                        vector = backend.get(name)
                        if vector is not None:
                            vector.destroy()
            if full_source is not None:
                full_source.destroy()
            for vector in (rhs, source):
                if vector is not None:
                    vector.destroy()
            if side_system is not None:
                side_system.destroy()

    if comm.rank == 0:
        print(
            json.dumps(
                {
                    'schema': 'task041.h1e.mpi8.side_backend_compare.summary.v1',
                    'mpi_size': int(comm.size),
                    'sides': [record['side'] for record in side_records],
                    'backend_sequence': 'bottom_then_top',
                },
                sort_keys=True,
            ),
            flush=True,
        )
