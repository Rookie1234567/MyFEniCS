"""Owner-local one-phase canonical relations for the B0-S1a fixture."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from mpi4py import MPI


@dataclass(frozen=True)
class SingleXPhaseLayout:
    owned_size: int
    local_size: int
    slave_local: np.ndarray
    master_local: np.ndarray
    coefficients: np.ndarray
    phase_x: complex
    global_slave_count: int
    global_phase_count: int
    global_cross_owner_count: int

@dataclass(frozen=True)
class PhaseApplication:
    values: np.ndarray
    phase_application_count: int

def build_single_x_phase_layout(function_space, mpc, phase_x: complex) -> SingleXPhaseLayout:
    phase = complex(phase_x)
    if not np.isfinite(phase) or abs(phase - 1.0) <= 1.0e-13:
        raise ValueError("phase_x must be finite and nontrivial")
    index_map = function_space.dofmap.index_map
    owned = int(index_map.size_local)
    local = owned + int(index_map.num_ghosts)
    mpc_index_map = mpc.function_space.dofmap.index_map
    owned_ids = np.arange(owned, dtype=np.int32)
    local_ids = np.arange(local, dtype=np.int32)
    if (owned, int(index_map.num_ghosts)) != (
        int(mpc_index_map.size_local), int(mpc_index_map.num_ghosts)
    ):
        raise RuntimeError("function-space and MPC ownership layouts differ")
    if not all(
        np.array_equal(index_map.local_to_global(ids), mpc_index_map.local_to_global(ids))
        for ids in (owned_ids, local_ids)
    ):
        raise RuntimeError("function-space and MPC ownership layouts differ")
    raw_slaves = np.asarray(mpc.slaves, dtype=np.int64)
    if len(np.unique(raw_slaves)) != len(raw_slaves) or np.any((raw_slaves < 0) | (raw_slaves >= local)):
        raise RuntimeError("MPC slave layout contains duplicate or invalid rows")
    slaves = np.sort(raw_slaves[(raw_slaves >= 0) & (raw_slaves < owned)])
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    slave_set = {int(value) for value in raw_slaves if 0 <= value < local}
    masters: list[int] = []
    phases: list[complex] = []
    phase_flags: list[bool] = []
    for slave in slaves:
        row = np.asarray(mpc.masters.links(int(slave)), dtype=np.int64)
        start, stop = int(offsets[slave]), int(offsets[slave + 1])
        if len(row) != 1 or stop - start != 1:
            raise RuntimeError("S1a requires exactly one master per slave")
        master = int(row[0])
        value = complex(coefficients[start])
        if not 0 <= master < local or master in slave_set:
            raise RuntimeError("MPC master ownership or chain is invalid")
        if not np.isfinite(value) or abs(value) <= 1.0e-14:
            raise RuntimeError("MPC phase coefficient is invalid")
        is_phase = np.isclose(value, phase, rtol=0.0, atol=1.0e-12) or np.isclose(
            value, -phase, rtol=0.0, atol=1.0e-12
        )
        is_unit = np.isclose(value, 1.0, rtol=0.0, atol=1.0e-12) or np.isclose(
            value, -1.0, rtol=0.0, atol=1.0e-12
        )
        if not (is_phase or is_unit):
            raise RuntimeError("MPC contains a phase other than x-phase or identity")
        masters.append(master)
        phases.append(value)
        phase_flags.append(bool(is_phase))
    comm = function_space.mesh.comm
    global_slave_count = int(comm.allreduce(len(slaves), op=MPI.SUM))
    global_phase_count = int(comm.allreduce(sum(phase_flags), op=MPI.SUM))
    global_cross_owner_count = int(comm.allreduce(sum(master >= owned for master in masters), op=MPI.SUM))
    if global_slave_count == 0 or global_phase_count == 0:
        raise RuntimeError("S1a requires at least one nontrivial x-phase slave")
    return SingleXPhaseLayout(
        owned_size=owned,
        local_size=local,
        slave_local=slaves,
        master_local=np.asarray(masters, dtype=np.int64),
        coefficients=np.asarray(phases, dtype=np.complex128),
        phase_x=phase,
        global_slave_count=global_slave_count,
        global_phase_count=global_phase_count,
        global_cross_owner_count=global_cross_owner_count,
    )

def _copy_values(values: np.ndarray, layout: SingleXPhaseLayout) -> np.ndarray:
    result = np.asarray(values, dtype=np.complex128)
    if result.ndim != 1 or len(result) != layout.local_size:
        raise ValueError("values must contain exactly owned and ghost entries")
    if not np.all(np.isfinite(result)):
        raise ValueError("values must be finite")
    return result.copy()

def canonicalize_envelope(values: np.ndarray, layout: SingleXPhaseLayout) -> np.ndarray:
    result = _copy_values(values, layout)
    result[layout.slave_local] = result[layout.master_local]
    return result

def apply_phase_once(values: np.ndarray, layout: SingleXPhaseLayout) -> PhaseApplication:
    result = _copy_values(values, layout)
    result[layout.slave_local] = layout.coefficients * result[layout.master_local]
    return PhaseApplication(result, 1)

def remove_phase_once(values: np.ndarray, layout: SingleXPhaseLayout) -> PhaseApplication:
    result = _copy_values(values, layout)
    result[layout.slave_local] /= layout.coefficients
    return PhaseApplication(result, 1)
