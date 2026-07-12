from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from petsc4py import PETSc


TINY = np.finfo(float).tiny


def condense_dense_blocks(
    F: np.ndarray,
    C: np.ndarray,
    D: np.ndarray,
    H: np.ndarray,
    b_fe: np.ndarray,
    b_aux: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the exact static condensation of an FE/auxiliary block system."""

    F = np.asarray(F, dtype=np.complex128)
    C = np.asarray(C, dtype=np.complex128)
    D = np.asarray(D, dtype=np.complex128)
    H = np.asarray(H, dtype=np.complex128)
    b_fe = np.asarray(b_fe, dtype=np.complex128)
    b_aux = np.asarray(b_aux, dtype=np.complex128)
    h_inv_d = np.linalg.solve(H, D)
    h_inv_b = np.linalg.solve(H, b_aux)
    return F - C @ h_inv_d, b_fe - C @ h_inv_b


def recover_dense_auxiliary(
    D: np.ndarray,
    H: np.ndarray,
    b_aux: np.ndarray,
    u_fe: np.ndarray,
) -> np.ndarray:
    """Recover auxiliary modal amplitudes after solving the condensed system."""

    return np.linalg.solve(
        np.asarray(H, dtype=np.complex128),
        np.asarray(b_aux, dtype=np.complex128)
        - np.asarray(D, dtype=np.complex128) @ np.asarray(u_fe, dtype=np.complex128),
    )


def _distributed_split_is(
    A_aug: PETSc.Mat, n_fe: int, n_aux: int
) -> tuple[PETSc.IS, PETSc.IS]:
    comm = A_aug.getComm()
    row_start, row_end = A_aug.getOwnershipRange()
    fe_indices = np.arange(max(row_start, 0), min(row_end, n_fe), dtype=PETSc.IntType)
    aux_indices = np.arange(
        max(row_start, n_fe), min(row_end, n_fe + n_aux), dtype=PETSc.IntType
    )
    return (
        PETSc.IS().createGeneral(fe_indices, comm=comm),
        PETSc.IS().createGeneral(aux_indices, comm=comm),
    )


def _copy_vector_segment(
    source: PETSc.Vec,
    target: PETSc.Vec,
    *,
    source_offset: int,
) -> None:
    local_start, local_end = target.getOwnershipRange()
    if local_end > local_start:
        target_indices = np.arange(local_start, local_end, dtype=PETSc.IntType)
        source_indices = target_indices + int(source_offset)
        target.setValues(target_indices, source.getValues(source_indices))
    target.assemble()


@dataclass
class PetscCondensedBlocks:
    F: PETSc.Mat
    C: PETSc.Mat
    D: PETSc.Mat
    H: PETSc.Mat
    b_fe: PETSc.Vec
    b_aux: PETSc.Vec
    n_fe: int
    n_aux: int

    def destroy(self) -> None:
        self.b_aux.destroy()
        self.b_fe.destroy()
        self.H.destroy()
        self.D.destroy()
        self.C.destroy()
        self.F.destroy()


def extract_petsc_condensed_blocks(
    A_aug: PETSc.Mat,
    b_aug: PETSc.Vec,
    *,
    n_fe: int,
    n_aux: int,
) -> PetscCondensedBlocks:
    """Extract distributed F/C/D/H blocks without gathering the FE matrix."""

    if A_aug.getSize() != (n_fe + n_aux, n_fe + n_aux):
        raise ValueError("augmented matrix dimensions do not match n_fe + n_aux")
    is_fe, is_aux = _distributed_split_is(A_aug, n_fe, n_aux)
    try:
        F = A_aug.createSubMatrix(is_fe, is_fe)
        C = A_aug.createSubMatrix(is_fe, is_aux)
        D = A_aug.createSubMatrix(is_aux, is_fe)
        H = A_aug.createSubMatrix(is_aux, is_aux)
    finally:
        is_fe.destroy()
        is_aux.destroy()
    b_fe = F.createVecLeft()
    b_aux = H.createVecLeft()
    _copy_vector_segment(b_aug, b_fe, source_offset=0)
    _copy_vector_segment(b_aug, b_aux, source_offset=n_fe)
    return PetscCondensedBlocks(F, C, D, H, b_fe, b_aux, int(n_fe), int(n_aux))


def gather_small_petsc_matrix(matrix: PETSc.Mat) -> np.ndarray:
    """Replicate a small distributed matrix with one collective per rank."""

    rows, cols = matrix.getSize()
    row_start, row_end = matrix.getOwnershipRange()
    local_rows = np.arange(row_start, row_end, dtype=PETSc.IntType)
    all_cols = np.arange(cols, dtype=PETSc.IntType)
    local = (
        np.asarray(matrix.getValues(local_rows, all_cols), dtype=np.complex128)
        if len(local_rows)
        else np.empty((0, cols), dtype=np.complex128)
    )
    mpi_comm = matrix.getComm().tompi4py()
    packets = mpi_comm.allgather((int(row_start), int(row_end), local))
    dense = np.empty((rows, cols), dtype=np.complex128)
    for start, end, values in packets:
        dense[start:end, :] = values
    return dense


class SmallDenseInverse:
    """Exact replicated inverse for the small modal H block."""

    def __init__(self, H: PETSc.Mat) -> None:
        self.H_dense = gather_small_petsc_matrix(H)
        self.condition_number = float(np.linalg.cond(self.H_dense))
        self.H_inverse = np.linalg.inv(self.H_dense)
        self.comm = H.getComm().tompi4py()

    def gather_vector(self, vector: PETSc.Vec) -> np.ndarray:
        start, end = vector.getOwnershipRange()
        local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
        packets = self.comm.allgather((int(start), int(end), local))
        result = np.empty(vector.getSize(), dtype=np.complex128)
        for packet_start, packet_end, values in packets:
            result[packet_start:packet_end] = values
        return result

    def solve(self, rhs: PETSc.Vec, solution: PETSc.Vec) -> None:
        values = self.H_inverse @ self.gather_vector(rhs)
        self._set_solution(values, solution)

    def solve_transpose(self, rhs: PETSc.Vec, solution: PETSc.Vec) -> None:
        values = self.H_inverse.T @ self.gather_vector(rhs)
        self._set_solution(values, solution)

    def solve_hermitian(self, rhs: PETSc.Vec, solution: PETSc.Vec) -> None:
        values = self.H_inverse.conjugate().T @ self.gather_vector(rhs)
        self._set_solution(values, solution)

    @staticmethod
    def _set_solution(values: np.ndarray, solution: PETSc.Vec) -> None:
        start, end = solution.getOwnershipRange()
        solution.getArray()[:] = values[start:end]


class CondensedDtnMatContext:
    """PETSc MatPython context for F - C H^{-1} D."""

    def __init__(self, blocks: PetscCondensedBlocks) -> None:
        self.blocks = blocks
        self.h_solver = SmallDenseInverse(blocks.H)
        self.d_work = blocks.D.createVecLeft()
        self.h_work = blocks.H.createVecLeft()
        self.c_work = blocks.C.createVecLeft()
        self.ct_work = blocks.C.createVecRight()
        self.ht_work = blocks.H.createVecRight()
        self.dt_work = blocks.D.createVecRight()
        self.apply_count = 0
        self.transpose_apply_count = 0
        self.hermitian_apply_count = 0
        self.destroyed = False

    def mult(self, _mat: PETSc.Mat, x: PETSc.Vec, y: PETSc.Vec) -> None:
        self.blocks.F.mult(x, y)
        self.blocks.D.mult(x, self.d_work)
        self.h_solver.solve(self.d_work, self.h_work)
        self.blocks.C.mult(self.h_work, self.c_work)
        y.axpy(PETSc.ScalarType(-1.0), self.c_work)
        self.apply_count += 1

    def multTranspose(self, _mat: PETSc.Mat, x: PETSc.Vec, y: PETSc.Vec) -> None:
        self.blocks.F.multTranspose(x, y)
        self.blocks.C.multTranspose(x, self.ct_work)
        self.h_solver.solve_transpose(self.ct_work, self.ht_work)
        self.blocks.D.multTranspose(self.ht_work, self.dt_work)
        y.axpy(PETSc.ScalarType(-1.0), self.dt_work)
        self.transpose_apply_count += 1

    def multHermitian(self, _mat: PETSc.Mat, x: PETSc.Vec, y: PETSc.Vec) -> None:
        self.blocks.F.multHermitian(x, y)
        self.blocks.C.multHermitian(x, self.ct_work)
        self.h_solver.solve_hermitian(self.ct_work, self.ht_work)
        self.blocks.D.multHermitian(self.ht_work, self.dt_work)
        y.axpy(PETSc.ScalarType(-1.0), self.dt_work)
        self.hermitian_apply_count += 1

    def destroy(self, _mat: PETSc.Mat | None = None) -> None:
        if self.destroyed:
            return
        self.dt_work.destroy()
        self.ht_work.destroy()
        self.ct_work.destroy()
        self.c_work.destroy()
        self.h_work.destroy()
        self.d_work.destroy()
        self.destroyed = True


def create_matrix_free_condensed_operator(
    blocks: PetscCondensedBlocks,
) -> tuple[PETSc.Mat, CondensedDtnMatContext]:
    context = CondensedDtnMatContext(blocks)
    matrix = PETSc.Mat().createPython(
        blocks.F.getSizes(), context=context, comm=blocks.F.getComm()
    )
    matrix.setUp()
    return matrix, context


def condensed_rhs(blocks: PetscCondensedBlocks) -> PETSc.Vec:
    h_inv_b = blocks.H.createVecRight()
    h_solver = SmallDenseInverse(blocks.H)
    h_solver.solve(blocks.b_aux, h_inv_b)
    correction = blocks.F.createVecLeft()
    blocks.C.mult(h_inv_b, correction)
    result = blocks.b_fe.copy()
    result.axpy(PETSc.ScalarType(-1.0), correction)
    correction.destroy()
    h_inv_b.destroy()
    return result


def build_explicit_condensed_operator(
    blocks: PetscCondensedBlocks,
) -> tuple[PETSc.Mat, PETSc.Mat]:
    """Build an explicit reference matrix; current 3D ports have H = I."""

    h_dense = gather_small_petsc_matrix(blocks.H)
    if not np.allclose(h_dense, np.eye(blocks.n_aux), rtol=0.0, atol=1.0e-13):
        raise NotImplementedError(
            "distributed explicit PETSc condensation currently requires the verified H=I port block"
        )
    port = blocks.C.matMult(blocks.D)
    port.scale(PETSc.ScalarType(-1.0))
    condensed = blocks.F.copy()
    condensed.axpy(
        PETSc.ScalarType(1.0),
        port,
        structure=PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN,
    )
    condensed.assemble()
    return condensed, port


def recover_petsc_auxiliary(
    blocks: PetscCondensedBlocks,
    u_fe: PETSc.Vec,
) -> PETSc.Vec:
    rhs = blocks.b_aux.copy()
    d_u = blocks.D.createVecLeft()
    blocks.D.mult(u_fe, d_u)
    rhs.axpy(PETSc.ScalarType(-1.0), d_u)
    result = blocks.H.createVecRight()
    SmallDenseInverse(blocks.H).solve(rhs, result)
    d_u.destroy()
    rhs.destroy()
    return result


def relative_action_error(
    reference: PETSc.Mat,
    candidate: PETSc.Mat,
    vector: PETSc.Vec,
) -> float:
    y_ref = reference.createVecLeft()
    y_candidate = candidate.createVecLeft()
    reference.mult(vector, y_ref)
    candidate.mult(vector, y_candidate)
    y_candidate.axpy(PETSc.ScalarType(-1.0), y_ref)
    error = float(y_candidate.norm() / max(float(y_ref.norm()), TINY))
    y_candidate.destroy()
    y_ref.destroy()
    return error


def matrix_storage_bytes(matrix: PETSc.Mat) -> float:
    info: dict[str, Any] = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
    reported = float(info.get("memory", 0.0))
    if reported > 0.0:
        return reported
    rows = int(matrix.getSize()[0])
    nnz = int(info.get("nz_used", 0.0))
    scalar_bytes = np.dtype(PETSc.ScalarType).itemsize
    index_bytes = np.dtype(PETSc.IntType).itemsize
    return float(nnz * (scalar_bytes + index_bytes) + (rows + 1) * index_bytes)
