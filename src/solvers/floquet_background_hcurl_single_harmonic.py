"""Single-harmonic Bloch phase and rank-three B0 MatPython helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .floquet_background_hcurl import maxwell_symbol_inverse


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


def _vector_layout(vector: PETSc.Vec):
    petsc_comm = vector.getComm()
    comm = petsc_comm.tompi4py()
    first, last = (int(value) for value in vector.getOwnershipRange())
    local = int(vector.getLocalSize())
    if local != last - first:
        raise RuntimeError("single-harmonic Q must have owned PETSc storage")
    return petsc_comm, comm, int(vector.getSize()), local, (first, last)


class SingleHarmonicMatPythonContext:
    def __init__(
        self,
        columns: Sequence[PETSc.Vec],
        wavevector: Sequence[float],
        *,
        mu_inv: complex,
        epsilon: complex,
        k0: float,
        shift: complex = 0.0j,
    ) -> None:
        if len(columns) != 3:
            raise ValueError("single-harmonic context requires exactly three Q columns")
        reference = columns[0]
        _, reference_comm, global_size, local_size, ownership = _vector_layout(reference)
        for column in columns:
            _, comm, candidate_global, candidate_local, candidate_ownership = _vector_layout(column)
            if MPI.Comm.Compare(reference_comm, comm) not in (MPI.IDENT, MPI.CONGRUENT):
                raise ValueError("Q columns use different communicators")
            if (candidate_global, candidate_local, candidate_ownership) != (
                global_size,
                local_size,
                ownership,
            ):
                raise ValueError("Q columns use different ownership layouts")
            if not np.all(np.isfinite(column.getArray(readonly=True))):
                raise ValueError("Q columns must be finite")
        self.columns = tuple(columns)
        self.global_size = global_size
        self.local_size = local_size
        self.ownership = ownership
        # PETSc Vec.dot(self, other) computes other^H self.
        self.gram = np.asarray(
            [
                [self.columns[j].dot(self.columns[i]) for j in range(3)]
                for i in range(3)
            ],
            dtype=np.complex128,
        )
        if not np.all(np.isfinite(self.gram)) or np.linalg.matrix_rank(self.gram) != 3:
            raise np.linalg.LinAlgError("single-harmonic Q Gram is singular")
        self.symbol_inverse = maxwell_symbol_inverse(
            wavevector,
            mu_inv=mu_inv,
            epsilon=epsilon,
            k0=k0,
            shift=shift,
        )
        self.apply_count = 0
        self.destroyed = False

    def mult(self, _matrix: PETSc.Mat, x: PETSc.Vec, y: PETSc.Vec) -> None:
        if self.destroyed:
            raise RuntimeError("single-harmonic context has been destroyed")
        d = np.asarray([x.dot(column) for column in self.columns], dtype=np.complex128)
        coefficients = np.linalg.solve(self.gram, d)
        transformed = self.symbol_inverse @ coefficients
        y.set(0.0)
        for value, column in zip(transformed, self.columns, strict=True):
            y.axpy(PETSc.ScalarType(value), column)
        self.apply_count += 1

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        self.destroyed = True


def create_single_harmonic_operator(
    columns: Sequence[PETSc.Vec],
    wavevector: Sequence[float],
    *,
    mu_inv: complex,
    epsilon: complex,
    k0: float,
    shift: complex = 0.0j,
) -> tuple[PETSc.Mat, SingleHarmonicMatPythonContext]:
    context = SingleHarmonicMatPythonContext(
        columns,
        wavevector,
        mu_inv=mu_inv,
        epsilon=epsilon,
        k0=k0,
        shift=shift,
    )
    petsc_comm = columns[0].getComm()
    size = ((context.local_size, context.global_size),) * 2
    matrix = PETSc.Mat().createPython(size, context=context, comm=petsc_comm)
    matrix.setUp()
    if tuple(matrix.getSize()) != (context.global_size,) * 2:
        matrix.destroy()
        raise RuntimeError("single-harmonic Mat has the wrong global size")
    if tuple(matrix.getLocalSize()) != (context.local_size,) * 2:
        matrix.destroy()
        raise RuntimeError("single-harmonic Mat has the wrong local size")
    ownership = tuple(int(value) for value in matrix.getOwnershipRange())
    if ownership != context.ownership:
        matrix.destroy()
        raise RuntimeError("single-harmonic Mat ownership differs from Q")
    return matrix, context
