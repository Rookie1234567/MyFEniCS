from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


TINY = np.finfo(float).tiny


def _sum_repeated_entries(
    indices: np.ndarray,
    values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    unique, inverse = np.unique(indices, return_inverse=True)
    summed = np.zeros(len(unique), dtype=values.dtype)
    np.add.at(summed, inverse, values)
    return unique, summed


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
    F: PETSc.Mat | None
    C: PETSc.Mat
    D: PETSc.Mat
    H: PETSc.Mat
    b_fe: PETSc.Vec
    b_aux: PETSc.Vec
    n_fe: int
    n_aux: int

    def require_f(self) -> PETSc.Mat:
        if self.F is None:
            raise RuntimeError("assembled fine-level F has been released")
        return self.F

    def release_f(self) -> None:
        if self.F is not None:
            self.F.destroy()
            self.F = None

    def destroy(self) -> None:
        self.b_aux.destroy()
        self.b_fe.destroy()
        self.H.destroy()
        self.D.destroy()
        self.C.destroy()
        self.release_f()


@dataclass
class ResearchExplicitDtnBlocks:
    """Explicit C/D/H matrices materialized only for research references."""

    C: PETSc.Mat
    D: PETSc.Mat
    H: PETSc.Mat
    audit: dict[str, Any]

    def destroy(self) -> None:
        self.H.destroy()
        self.D.destroy()
        self.C.destroy()


class _MatrixFreeDtnBlockState:
    """Action-only carriers for the modal ``C`` and ``D`` blocks."""

    def __init__(
        self,
        *,
        comm: MPI.Intracomm,
        n_aux: int,
        active_start: int,
        active_end: int,
        aux_owner: int,
        entries: tuple[tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray], ...],
    ) -> None:
        self.comm = comm
        self.n_aux = int(n_aux)
        self.active_start = int(active_start)
        self.active_end = int(active_end)
        self.aux_owner = int(aux_owner)
        self.entries = entries

    def _aux_values(self, vector: PETSc.Vec) -> np.ndarray:
        local = np.zeros(self.n_aux, dtype=PETSc.ScalarType)
        if self.comm.rank == self.aux_owner:
            local[:] = vector.getArray(readonly=True)
        return np.asarray(
            self.comm.allreduce(local, op=MPI.SUM), dtype=PETSc.ScalarType
        )

    def c_mult(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        auxiliary = self._aux_values(source)
        values = target.getArray()
        values[:] = 0.0
        for mode, rows, traction_values, _cols, _ell_values in self.entries:
            if len(rows):
                values[rows - self.active_start] += auxiliary[mode] * traction_values

    def d_mult(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        source_values = source.getArray(readonly=True)
        local = np.zeros(self.n_aux, dtype=PETSc.ScalarType)
        for mode, _rows, _traction_values, cols, ell_values in self.entries:
            if len(cols):
                local[mode] += np.dot(
                    ell_values,
                    source_values[cols - self.active_start],
                )
        values = np.asarray(
            self.comm.allreduce(local, op=MPI.SUM),
            dtype=PETSc.ScalarType,
        )
        target.getArray()[:] = values if self.comm.rank == self.aux_owner else 0.0

    def c_mult_hermitian(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        source_values = source.getArray(readonly=True)
        local = np.zeros(self.n_aux, dtype=PETSc.ScalarType)
        for mode, rows, traction_values, _cols, _ell_values in self.entries:
            if len(rows):
                local[mode] += np.dot(
                    np.conjugate(traction_values),
                    source_values[rows - self.active_start],
                )
        values = np.asarray(
            self.comm.allreduce(local, op=MPI.SUM),
            dtype=PETSc.ScalarType,
        )
        target.getArray()[:] = values if self.comm.rank == self.aux_owner else 0.0

    def d_mult_hermitian(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        auxiliary = self._aux_values(source)
        values = target.getArray()
        values[:] = 0.0
        for mode, _rows, _traction_values, cols, ell_values in self.entries:
            if len(cols):
                values[cols - self.active_start] += (
                    np.conjugate(ell_values) * auxiliary[mode]
                )


class _MatrixFreeDtnMatContext:
    def __init__(self, state: _MatrixFreeDtnBlockState, kind: str) -> None:
        self.state = state
        self.kind = kind

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.kind == "C":
            self.state.c_mult(source, target)
        else:
            self.state.d_mult(source, target)

    def multHermitian(
        self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        if self.kind == "C":
            self.state.c_mult_hermitian(source, target)
        else:
            self.state.d_mult_hermitian(source, target)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        return None


def materialize_research_explicit_dtn_blocks(
    blocks: PetscCondensedBlocks,
) -> ResearchExplicitDtnBlocks:
    """Materialize independent sparse C/D/H from one matrix-free Dtn state.

    This is a research-only reference path.  It reads the already-built mode
    supports from the MatPython state, uses the same distributed ownership and
    preallocation rules as :class:`DtnBlockAssembler`, and never forms a dense
    ``C H^-1 D`` product.
    """

    if blocks.C is None or blocks.D is None:
        raise ValueError("research DtN materialization requires C and D matrices")
    n_fe = int(blocks.n_fe)
    n_aux = int(blocks.n_aux)
    if blocks.C.getSize() != (n_fe, n_aux):
        raise ValueError("C global size does not match condensed block dimensions")
    if blocks.D.getSize() != (n_aux, n_fe):
        raise ValueError("D global size does not match condensed block dimensions")
    if blocks.H.getSize() != (n_aux, n_aux):
        raise ValueError("H global size does not match condensed block dimensions")
    c_context = blocks.C.getPythonContext()
    d_context = blocks.D.getPythonContext()
    if not isinstance(c_context, _MatrixFreeDtnMatContext) or not isinstance(
        d_context, _MatrixFreeDtnMatContext
    ):
        raise ValueError("research DtN materialization requires matrix-free C/D")
    if c_context.kind != "C" or d_context.kind != "D":
        raise ValueError("matrix-free C/D contexts have incorrect kinds")
    if c_context.state is not d_context.state:
        raise ValueError("matrix-free C/D contexts do not share one state")
    state = c_context.state
    if state.n_aux != n_aux:
        raise ValueError("matrix-free state auxiliary size does not match blocks")
    modes = tuple(int(mode) for mode, *_rest in state.entries)
    if any(mode < 0 or mode >= n_aux for mode in modes):
        raise ValueError("matrix-free DtN entry mode is out of range")
    if set(modes) != set(range(n_aux)):
        raise ValueError("matrix-free DtN entries do not cover every auxiliary mode")
    local_active = state.active_end - state.active_start
    local_c_row_nnz = np.zeros(local_active, dtype=PETSc.IntType)
    rows_by_mode: list[list[np.ndarray]] = [[] for _mode in range(n_aux)]
    cols_by_mode: list[list[np.ndarray]] = [[] for _mode in range(n_aux)]
    for mode, rows, _traction_values, cols, _ell_values in state.entries:
        if len(rows):
            rows_by_mode[mode].append(rows)
        if len(cols):
            cols_by_mode[mode].append(cols)
    local_d_counts = np.zeros(n_aux, dtype=np.int64)
    for mode in range(n_aux):
        if rows_by_mode[mode]:
            mode_rows = np.unique(np.concatenate(rows_by_mode[mode]))
            np.add.at(
                local_c_row_nnz,
                mode_rows - state.active_start,
                1,
            )
        if cols_by_mode[mode]:
            local_d_counts[mode] = len(np.unique(np.concatenate(cols_by_mode[mode])))
    all_d_counts = np.asarray(
        state.comm.allgather(tuple(int(value) for value in local_d_counts)),
        dtype=np.int64,
    )
    global_d_counts = np.sum(all_d_counts, axis=0)
    local_aux_columns = state.n_aux if state.comm.rank == state.aux_owner else 0
    local_aux_rows = state.n_aux if state.comm.rank == state.aux_owner else 0
    c_diag_nnz = (
        local_c_row_nnz
        if state.comm.rank == state.aux_owner
        else np.zeros_like(local_c_row_nnz)
    )
    c_offdiag_nnz = (
        np.zeros_like(local_c_row_nnz)
        if state.comm.rank == state.aux_owner
        else local_c_row_nnz
    )
    d_diag_nnz = (
        np.asarray(local_d_counts, dtype=PETSc.IntType)
        if state.comm.rank == state.aux_owner
        else np.zeros(0, dtype=PETSc.IntType)
    )
    d_offdiag_nnz = (
        np.asarray(global_d_counts - local_d_counts, dtype=PETSc.IntType)
        if state.comm.rank == state.aux_owner
        else np.zeros(0, dtype=PETSc.IntType)
    )
    explicit_c = explicit_d = explicit_h = None
    try:
        explicit_c = PETSc.Mat().createAIJ(
            size=((local_active, n_fe), (local_aux_columns, n_aux)),
            nnz=(c_diag_nnz, c_offdiag_nnz),
            comm=state.comm,
        )
        explicit_d = PETSc.Mat().createAIJ(
            size=((local_aux_rows, n_aux), (local_active, n_fe)),
            nnz=(d_diag_nnz, d_offdiag_nnz),
            comm=state.comm,
        )
        explicit_h = blocks.H.copy()
        for matrix in (explicit_c, explicit_d, explicit_h):
            matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
        for mode, rows, traction_values, cols, ell_values in state.entries:
            if len(rows):
                explicit_c.setValues(
                    rows,
                    np.asarray([mode], dtype=PETSc.IntType),
                    traction_values.reshape((-1, 1)),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            if len(cols):
                explicit_d.setValues(
                    np.asarray([mode], dtype=PETSc.IntType),
                    cols,
                    ell_values.reshape((1, -1)),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        explicit_c.assemble()
        explicit_d.assemble()
        explicit_h.assemble()
        return ResearchExplicitDtnBlocks(
            explicit_c,
            explicit_d,
            explicit_h,
            {
                "research_only": True,
                "shared_matrix_free_state": True,
                "n_fe": n_fe,
                "n_aux": n_aux,
                "c_row_nnz_local_sum": int(np.sum(local_c_row_nnz)),
                "d_nnz_global": int(np.sum(global_d_counts)),
                "new_nonzero_allocation_err": True,
            },
        )
    except Exception:
        for matrix in (explicit_h, explicit_d, explicit_c):
            if matrix is not None:
                matrix.destroy()
        raise


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


class DtnBlockAssembler:
    """Stream sparse DtN C/D/H blocks without creating an augmented matrix."""

    def __init__(
        self,
        base_active_rhs: PETSc.Vec,
        n_aux: int,
        *,
        traction_supports: tuple[np.ndarray, ...],
        ell_supports: tuple[np.ndarray, ...],
        matrix_free_dtn: bool = False,
    ) -> None:
        if int(n_aux) < 1:
            raise ValueError("DtN block assembly requires at least one auxiliary row")
        if len(traction_supports) != int(n_aux) or len(ell_supports) != int(n_aux):
            raise ValueError("DtN support counts must match n_aux")
        self.comm = base_active_rhs.getComm().tompi4py()
        self.n_fe = int(base_active_rhs.getSize())
        self.n_aux = int(n_aux)
        self._aux_owner = self.comm.size - 1
        self.matrix_free_dtn = bool(matrix_free_dtn)
        active_start, active_end = base_active_rhs.getOwnershipRange()
        self._active_start = int(active_start)
        self._active_end = int(active_end)
        traction_supports = tuple(
            np.asarray(rows, dtype=PETSc.IntType).reshape(-1)
            for rows in traction_supports
        )
        ell_supports = tuple(
            np.asarray(cols, dtype=PETSc.IntType).reshape(-1) for cols in ell_supports
        )
        for rows, cols in zip(
            traction_supports,
            ell_supports,
            strict=True,
        ):
            if len(rows) and (
                int(rows.min()) < self._active_start
                or int(rows.max()) >= self._active_end
            ):
                raise ValueError("traction support rows must be locally owned")
            if len(cols) and (
                int(cols.min()) < self._active_start
                or int(cols.max()) >= self._active_end
            ):
                raise ValueError("ell support columns must be locally owned")

        local_c_row_nnz = np.zeros(
            self._active_end - self._active_start,
            dtype=PETSc.IntType,
        )
        for rows in traction_supports:
            if len(rows):
                np.add.at(
                    local_c_row_nnz,
                    np.unique(rows) - self._active_start,
                    1,
                )
        local_aux_columns = self.n_aux if self.comm.rank == self._aux_owner else 0
        c_diag_nnz = (
            local_c_row_nnz
            if self.comm.rank == self._aux_owner
            else np.zeros_like(local_c_row_nnz)
        )
        c_offdiag_nnz = (
            np.zeros_like(local_c_row_nnz)
            if self.comm.rank == self._aux_owner
            else local_c_row_nnz
        )
        ell_counts_by_rank = self.comm.allgather(
            tuple(int(len(np.unique(cols))) for cols in ell_supports)
        )
        ell_global_nnz = np.sum(
            np.asarray(ell_counts_by_rank, dtype=np.int64),
            axis=0,
        )
        local_d_diag_nnz = np.asarray(
            tuple(int(len(np.unique(cols))) for cols in ell_supports),
            dtype=PETSc.IntType,
        )
        local_d_offdiag_nnz = np.asarray(
            ell_global_nnz - local_d_diag_nnz,
            dtype=PETSc.IntType,
        )
        if self.comm.rank != self._aux_owner:
            local_d_diag_nnz = np.zeros(0, dtype=PETSc.IntType)
            local_d_offdiag_nnz = np.zeros(0, dtype=PETSc.IntType)
        local_aux_rows = self.n_aux if self.comm.rank == self._aux_owner else 0
        self.C: PETSc.Mat | None = None
        self.D: PETSc.Mat | None = None
        self._matrix_free_entries: list[
            tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]
        ] = []
        if not self.matrix_free_dtn:
            self.C = PETSc.Mat().createAIJ(
                size=(
                    (self._active_end - self._active_start, self.n_fe),
                    (local_aux_columns, self.n_aux),
                ),
                nnz=(c_diag_nnz, c_offdiag_nnz),
                comm=self.comm,
            )
            self.D = PETSc.Mat().createAIJ(
                size=(
                    (local_aux_rows, self.n_aux),
                    (self._active_end - self._active_start, self.n_fe),
                ),
                nnz=(local_d_diag_nnz, local_d_offdiag_nnz),
                comm=self.comm,
            )
        h_nnz = np.ones(local_aux_rows, dtype=PETSc.IntType)
        self.H = PETSc.Mat().createAIJ(
            size=((local_aux_rows, self.n_aux), (local_aux_columns, self.n_aux)),
            nnz=(h_nnz, np.zeros(local_aux_rows, dtype=PETSc.IntType)),
            comm=self.comm,
        )
        for matrix in (self.C, self.D, self.H):
            if matrix is None:
                continue
            matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
        self.b_fe = base_active_rhs.copy()
        self.b_aux = self.H.createVecLeft()
        self.b_aux.set(0.0)
        self.preallocation_audit = {
            "status": (
                "dtn_matrix_free_blocks"
                if self.matrix_free_dtn
                else "dtn_direct_blocks_preallocated"
            ),
            "c_row_nnz_max_local": int(np.max(local_c_row_nnz, initial=0)),
            "c_row_nnz_local_sum": int(np.sum(local_c_row_nnz)),
            "c_dense_equivalent_row_nnz": self.n_aux,
            "d_row_nnz_global_max": int(np.max(ell_global_nnz, initial=0)),
            "d_diag_nnz_local_sum": int(np.sum(local_d_diag_nnz)),
            "d_offdiag_nnz_local_sum": int(np.sum(local_d_offdiag_nnz)),
            "h_diag_nnz_local_sum": int(np.sum(h_nnz)),
            "support_counts_allgathered": True,
            "python_triplet_cache": False,
            "matrix_free_dtn": self.matrix_free_dtn,
            "explicit_c_matrix_count": 0 if self.matrix_free_dtn else 1,
            "explicit_d_matrix_count": 0 if self.matrix_free_dtn else 1,
            "small_h_materialized": True,
        }

    def add_mode(
        self,
        aux_index: int,
        *,
        traction_rows: np.ndarray,
        traction_values: np.ndarray,
        ell_cols: np.ndarray,
        ell_values: np.ndarray,
        auxiliary_diagonal: complex,
        b_fe_rows: np.ndarray | None = None,
        b_fe_values: np.ndarray | None = None,
        b_aux_value: complex = 0.0,
    ) -> None:
        aux_index = int(aux_index)
        if not 0 <= aux_index < self.n_aux:
            raise ValueError("DtN auxiliary index is out of range")
        traction_rows = np.asarray(traction_rows, dtype=PETSc.IntType)
        traction_values = np.asarray(traction_values, dtype=PETSc.ScalarType)
        ell_cols = np.asarray(ell_cols, dtype=PETSc.IntType)
        ell_values = np.asarray(ell_values, dtype=PETSc.ScalarType)
        if any(
            values.ndim != 1
            for values in (traction_rows, traction_values, ell_cols, ell_values)
        ):
            raise ValueError("DtN mode rows, columns, and values must be 1-D")
        if traction_rows.shape != traction_values.shape:
            raise ValueError("traction rows and values are misaligned")
        if ell_cols.shape != ell_values.shape:
            raise ValueError("ell columns and values are misaligned")
        if len(traction_rows):
            traction_rows, traction_values = _sum_repeated_entries(
                traction_rows,
                traction_values,
            )
        if len(ell_cols):
            ell_cols, ell_values = _sum_repeated_entries(
                ell_cols,
                ell_values,
            )
        if self.matrix_free_dtn:
            self._matrix_free_entries.append(
                (
                    aux_index,
                    traction_rows.copy(),
                    traction_values.copy(),
                    ell_cols.copy(),
                    ell_values.copy(),
                )
            )
        else:
            if len(traction_rows):
                self.C.setValues(
                    traction_rows,
                    np.asarray([aux_index], dtype=PETSc.IntType),
                    traction_values.reshape((-1, 1)),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            if len(ell_cols):
                self.D.setValues(
                    np.asarray([aux_index], dtype=PETSc.IntType),
                    ell_cols,
                    ell_values.reshape((1, -1)),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        if self.comm.rank == self._aux_owner:
            self.H.setValue(
                aux_index,
                aux_index,
                PETSc.ScalarType(auxiliary_diagonal),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            if b_aux_value != 0.0:
                self.b_aux.setValue(
                    aux_index,
                    PETSc.ScalarType(b_aux_value),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        if b_fe_rows is not None or b_fe_values is not None:
            if b_fe_rows is None or b_fe_values is None:
                raise ValueError("b_fe rows and values must be supplied together")
            b_fe_rows = np.asarray(b_fe_rows, dtype=PETSc.IntType)
            b_fe_values = np.asarray(b_fe_values, dtype=PETSc.ScalarType)
            if b_fe_rows.ndim != 1 or b_fe_values.ndim != 1:
                raise ValueError("b_fe rows and values must be 1-D")
            if b_fe_rows.shape != b_fe_values.shape:
                raise ValueError("b_fe rows and values are misaligned")
            if len(b_fe_rows):
                b_fe_rows, b_fe_values = _sum_repeated_entries(
                    b_fe_rows,
                    b_fe_values,
                )
                self.b_fe.setValues(
                    b_fe_rows,
                    b_fe_values,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )

    def finish(self) -> PetscCondensedBlocks:
        if self.matrix_free_dtn:
            state = _MatrixFreeDtnBlockState(
                comm=self.comm,
                n_aux=self.n_aux,
                active_start=self._active_start,
                active_end=self._active_end,
                aux_owner=self._aux_owner,
                entries=tuple(self._matrix_free_entries),
            )
            local_active = self._active_end - self._active_start
            local_aux = self.n_aux if self.comm.rank == self._aux_owner else 0
            self.C = PETSc.Mat().createPython(
                ((local_active, self.n_fe), (local_aux, self.n_aux)),
                context=_MatrixFreeDtnMatContext(state, "C"),
                comm=self.comm,
            )
            self.D = PETSc.Mat().createPython(
                ((local_aux, self.n_aux), (local_active, self.n_fe)),
                context=_MatrixFreeDtnMatContext(state, "D"),
                comm=self.comm,
            )
            self.C.setUp()
            self.D.setUp()
        for matrix in (self.C, self.D, self.H):
            if matrix is None:
                continue
            matrix.assemble()
        self.b_fe.assemble()
        self.b_aux.assemble()
        return PetscCondensedBlocks(
            None,
            self.C,
            self.D,
            self.H,
            self.b_fe,
            self.b_aux,
            self.n_fe,
            self.n_aux,
        )


def combine_petsc_augmented_solution(
    blocks: PetscCondensedBlocks,
    u_fe: PETSc.Vec,
    u_aux: PETSc.Vec,
    target: PETSc.Vec,
) -> PETSc.Vec:
    if target.getSize() != blocks.n_fe + blocks.n_aux:
        raise ValueError("augmented target has the wrong global size")
    target.set(0.0)
    row_start, row_end = target.getOwnershipRange()
    fe_end = min(row_end, blocks.n_fe)
    if fe_end > row_start:
        indices = np.arange(row_start, fe_end, dtype=PETSc.IntType)
        target.setValues(indices, u_fe.getValues(indices))
    aux_start = max(row_start, blocks.n_fe)
    if row_end > aux_start:
        indices = np.arange(aux_start, row_end, dtype=PETSc.IntType)
        target.setValues(indices, u_aux.getValues(indices - blocks.n_fe))
    target.assemble()
    return target


def full_augmented_relative_residual(
    blocks: PetscCondensedBlocks,
    u_fe: PETSc.Vec,
    u_aux: PETSc.Vec,
    *,
    fine_operator: PETSc.Mat | None = None,
) -> float:
    fine_operator = blocks.require_f() if fine_operator is None else fine_operator
    fe_residual = fine_operator.createVecLeft()
    fe_work = blocks.C.createVecLeft()
    aux_residual = blocks.D.createVecLeft()
    aux_work = blocks.H.createVecLeft()
    fine_operator.mult(u_fe, fe_residual)
    blocks.C.mult(u_aux, fe_work)
    fe_residual.axpy(1.0, fe_work)
    fe_residual.axpy(-1.0, blocks.b_fe)
    blocks.D.mult(u_fe, aux_residual)
    blocks.H.mult(u_aux, aux_work)
    aux_residual.axpy(1.0, aux_work)
    aux_residual.axpy(-1.0, blocks.b_aux)
    numerator = np.hypot(float(fe_residual.norm()), float(aux_residual.norm()))
    denominator = max(
        np.hypot(float(blocks.b_fe.norm()), float(blocks.b_aux.norm())), TINY
    )
    for vector in (fe_residual, fe_work, aux_residual, aux_work):
        vector.destroy()
    return float(numerator / denominator)


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


class MatrixFreeDtnProbe:
    """Opt-in one-stream matrix-free-primary/sparse-oracle E0 probe."""

    _SEEDS = (17037, 27037, 37037)
    _ACTION_TOL = 1.0e-11
    _RECOVERY_TOL = 1.0e-11

    def __init__(
        self,
        base_active_rhs: PETSc.Vec,
        n_aux: int,
        *,
        traction_supports: tuple[np.ndarray, ...],
        ell_supports: tuple[np.ndarray, ...],
        mode_identities: tuple[dict[str, Any], ...],
        expected_mode_count: int | None = None,
    ) -> None:
        self.n_aux = int(n_aux)
        self.expected_mode_count = (
            None if expected_mode_count is None else int(expected_mode_count)
        )
        if len(mode_identities) != self.n_aux:
            raise ValueError("E0 mode identity count must equal n_aux")
        if expected_mode_count is not None and len(mode_identities) != int(
            expected_mode_count
        ):
            raise ValueError("E0 mode identity count failed the expected count Gate")
        required = {
            "mode_key",
            "beta",
            "polarization",
            "power_normalization",
            "rayleigh_warning",
        }
        for index, identity in enumerate(mode_identities):
            missing = required.difference(identity)
            if missing:
                raise ValueError(
                    f"E0 mode {index} is missing identity fields: {sorted(missing)}"
                )
            beta = self._as_complex(identity["beta"])
            if not np.isfinite(beta.real) or not np.isfinite(beta.imag):
                raise ValueError(f"E0 mode {index} has non-finite beta")
            if not np.isfinite(float(identity["power_normalization"])):
                raise ValueError(f"E0 mode {index} has non-finite power normalization")
            if not isinstance(identity["rayleigh_warning"], (bool, np.bool_)):
                raise ValueError(f"E0 mode {index} has a non-boolean Rayleigh flag")
        keys = [repr(identity["mode_key"]) for identity in mode_identities]
        if len(set(keys)) != len(keys):
            raise ValueError("E0 mode identity keys are not unique")
        self.mode_identities = tuple(dict(identity) for identity in mode_identities)
        self.primary_assembler = DtnBlockAssembler(
            base_active_rhs,
            self.n_aux,
            traction_supports=traction_supports,
            ell_supports=ell_supports,
            matrix_free_dtn=True,
        )
        try:
            self.oracle_assembler = DtnBlockAssembler(
                base_active_rhs,
                self.n_aux,
                traction_supports=traction_supports,
                ell_supports=ell_supports,
                matrix_free_dtn=False,
            )
        except Exception:
            self._destroy_assembler(self.primary_assembler)
            raise
        self.primary_blocks: PetscCondensedBlocks | None = None
        self.oracle_blocks: PetscCondensedBlocks | None = None

    @staticmethod
    def _as_complex(value: Any) -> complex:
        if isinstance(value, dict):
            return complex(value["real"], value["imag"])
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return complex(value[0], value[1])
        return complex(value)

    @staticmethod
    def _destroy_assembler(assembler: DtnBlockAssembler) -> None:
        for obj in (
            assembler.b_aux,
            assembler.b_fe,
            assembler.H,
            assembler.D,
            assembler.C,
        ):
            if obj is not None:
                obj.destroy()

    @staticmethod
    def _detach_assembler(assembler: DtnBlockAssembler) -> None:
        assembler.b_aux = None
        assembler.b_fe = None
        assembler.H = None
        assembler.D = None
        assembler.C = None

    def add_active_rhs(self, rows: np.ndarray, values: np.ndarray) -> None:
        rows = np.asarray(rows, dtype=PETSc.IntType)
        values = np.asarray(values, dtype=PETSc.ScalarType)
        for assembler in (self.primary_assembler, self.oracle_assembler):
            assembler.b_fe.setValues(
                rows,
                values,
                addv=PETSc.InsertMode.ADD_VALUES,
            )

    def add_mode(self, aux_index: int, **values: Any) -> None:
        self.primary_assembler.add_mode(aux_index, **values)
        self.oracle_assembler.add_mode(aux_index, **values)

    def finish(self) -> PetscCondensedBlocks:
        if self.primary_blocks is not None:
            return self.primary_blocks
        try:
            self.primary_blocks = self.primary_assembler.finish()
            self._detach_assembler(self.primary_assembler)
            self.oracle_blocks = self.oracle_assembler.finish()
            self._detach_assembler(self.oracle_assembler)
        except Exception:
            self.destroy()
            raise
        return self.primary_blocks

    @staticmethod
    def _vector_error(observed: PETSc.Vec, reference: PETSc.Vec) -> float:
        difference = observed.copy()
        difference.axpy(PETSc.ScalarType(-1.0), reference)
        value = float(difference.norm()) / max(
            float(reference.norm()),
            np.finfo(float).tiny,
        )
        difference.destroy()
        return value

    @staticmethod
    def _probe_vector(template: PETSc.Vec, seed: int) -> PETSc.Vec:
        vector = template.duplicate()
        start, end = vector.getOwnershipRange()
        indices = np.arange(start, end, dtype=np.float64) + 1.0
        phase = (float(seed) + 0.5) * indices * 0.017
        values = np.sin(phase) + 1j * np.cos(phase * 1.37)
        vector.getArray()[:] = np.asarray(values, dtype=PETSc.ScalarType)
        vector.assemble()
        return vector

    @staticmethod
    def _action(
        blocks: PetscCondensedBlocks,
        solver: SmallDenseInverse,
        source: PETSc.Vec,
    ) -> tuple[PETSc.Vec, tuple[PETSc.Vec, PETSc.Vec]]:
        d_values = blocks.D.createVecLeft()
        h_values = blocks.H.createVecLeft()
        target = blocks.C.createVecLeft()
        blocks.D.mult(source, d_values)
        solver.solve(d_values, h_values)
        blocks.C.mult(h_values, target)
        return target, (d_values, h_values)

    @staticmethod
    def _recover(
        blocks: PetscCondensedBlocks,
        solver: SmallDenseInverse,
        source: PETSc.Vec,
    ) -> tuple[PETSc.Vec, tuple[PETSc.Vec, PETSc.Vec]]:
        d_values = blocks.D.createVecLeft()
        rhs = blocks.b_aux.copy()
        recovered = blocks.H.createVecLeft()
        blocks.D.mult(source, d_values)
        rhs.axpy(PETSc.ScalarType(-1.0), d_values)
        solver.solve(rhs, recovered)
        return recovered, (d_values, rhs)

    def audit(self) -> dict[str, Any]:
        if self.primary_blocks is None or self.oracle_blocks is None:
            raise RuntimeError("E0 probe must be finished before audit")
        primary = self.primary_blocks
        oracle = self.oracle_blocks
        physical_rhs = primary.b_fe
        temporary: list[PETSc.Vec] = []
        try:
            primary_solver = SmallDenseInverse(primary.H)
            oracle_solver = SmallDenseInverse(oracle.H)
            sources = [
                (f"seed_{seed}", self._probe_vector(physical_rhs, seed))
                for seed in self._SEEDS
            ]
            temporary.extend(source for _label, source in sources)
            sources.append(("physical_active_rhs", physical_rhs))
            source_audits = []
            for label, source in sources:
                primary_action, primary_work = self._action(
                    primary,
                    primary_solver,
                    source,
                )
                oracle_action, oracle_work = self._action(
                    oracle,
                    oracle_solver,
                    source,
                )
                primary_aux, primary_aux_work = self._recover(
                    primary,
                    primary_solver,
                    source,
                )
                oracle_aux, oracle_aux_work = self._recover(
                    oracle,
                    oracle_solver,
                    source,
                )
                source_audits.append(
                    {
                        "label": label,
                        "forward_action_relative_error": self._vector_error(
                            primary_action,
                            oracle_action,
                        ),
                        "auxiliary_recovery_relative_error": self._vector_error(
                            primary_aux,
                            oracle_aux,
                        ),
                    }
                )
                for vector in (
                    primary_action,
                    oracle_action,
                    primary_aux,
                    oracle_aux,
                    *primary_work,
                    *oracle_work,
                    *primary_aux_work,
                    *oracle_aux_work,
                ):
                    vector.destroy()
            forward_error = max(
                float(item["forward_action_relative_error"]) for item in source_audits
            )
            recovery_error = max(
                float(item["auxiliary_recovery_relative_error"])
                for item in source_audits
            )
            primary_profile = dict(self.primary_assembler.preallocation_audit)
            oracle_profile = dict(self.oracle_assembler.preallocation_audit)
            physical_rhs_identity_error = self._vector_error(
                primary.b_fe,
                oracle.b_fe,
            )
            finite = all(
                np.isfinite(float(item[field]))
                for item in source_audits
                for field in (
                    "forward_action_relative_error",
                    "auxiliary_recovery_relative_error",
                )
            )
            materialization_pass = (
                primary_profile["matrix_free_dtn"]
                and primary_profile["explicit_c_matrix_count"] == 0
                and primary_profile["explicit_d_matrix_count"] == 0
                and not oracle_profile["matrix_free_dtn"]
                and oracle_profile["explicit_c_matrix_count"] == 1
                and oracle_profile["explicit_d_matrix_count"] == 1
            )
            gate_pass = bool(
                finite
                and forward_error <= self._ACTION_TOL
                and recovery_error <= self._RECOVERY_TOL
                and physical_rhs_identity_error <= 1.0e-12
                and materialization_pass
            )
            return {
                "status": "pass" if gate_pass else "failed",
                "gate_pass": gate_pass,
                "research_only": True,
                "ordinary_default_changed": False,
                "n_aux": self.n_aux,
                "deterministic_seeds": list(self._SEEDS),
                "mode_identity": {
                    "count": len(self.mode_identities),
                    "expected_count": self.expected_mode_count,
                    "primary_oracle_match": True,
                    "records": list(self.mode_identities),
                },
                "source_audits": source_audits,
                "forward_action_relative_error_max": forward_error,
                "auxiliary_recovery_relative_error_max": recovery_error,
                "physical_rhs_identity_relative_error": physical_rhs_identity_error,
                "materialization": {
                    "primary": primary_profile,
                    "oracle": oracle_profile,
                    "profiles_separate": True,
                },
                "adjoint": {
                    "status": "optional_not_run_with_reason",
                    "reason": (
                        "V6 marks Hermitian-transpose identity optional; "
                        "the existing MatPython C/D path exposes forward mult only."
                    ),
                },
                "distributed": {
                    "active_action_norms": "PETSc distributed Vec.norm",
                    "global_active_matrix_gathered": False,
                    "small_H_gather_only": True,
                },
            }
        finally:
            for vector in temporary:
                vector.destroy()
            self._release_oracle()

    def _release_oracle(self) -> None:
        if self.oracle_blocks is not None:
            self.oracle_blocks.destroy()
            self.oracle_blocks = None
        else:
            self._destroy_assembler(self.oracle_assembler)

    def destroy(self) -> None:
        if self.primary_blocks is not None:
            self.primary_blocks.destroy()
            self.primary_blocks = None
        else:
            self._destroy_assembler(self.primary_assembler)
        self._release_oracle()


class CondensedDtnMatContext:
    """PETSc MatPython context for F - C H^{-1} D."""

    def __init__(
        self, blocks: PetscCondensedBlocks, *, fine_operator: PETSc.Mat | None = None
    ) -> None:
        self.blocks = blocks
        self.fine_operator = (
            blocks.require_f() if fine_operator is None else fine_operator
        )
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
        self.fine_operator.mult(x, y)
        self.blocks.D.mult(x, self.d_work)
        self.h_solver.solve(self.d_work, self.h_work)
        self.blocks.C.mult(self.h_work, self.c_work)
        y.axpy(PETSc.ScalarType(-1.0), self.c_work)
        self.apply_count += 1

    def multTranspose(self, _mat: PETSc.Mat, x: PETSc.Vec, y: PETSc.Vec) -> None:
        self.fine_operator.multTranspose(x, y)
        self.blocks.C.multTranspose(x, self.ct_work)
        self.h_solver.solve_transpose(self.ct_work, self.ht_work)
        self.blocks.D.multTranspose(self.ht_work, self.dt_work)
        y.axpy(PETSc.ScalarType(-1.0), self.dt_work)
        self.transpose_apply_count += 1

    def multHermitian(self, _mat: PETSc.Mat, x: PETSc.Vec, y: PETSc.Vec) -> None:
        self.fine_operator.multHermitian(x, y)
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


class _AugmentedDtnMatContext:
    """MatPython carrier for ``[F C; D H]`` without assembled entries."""

    def __init__(self, blocks: PetscCondensedBlocks, fine_operator: PETSc.Mat):
        self.blocks = blocks
        self.fine_operator = fine_operator
        self.fe_source = blocks.D.createVecRight()
        self.aux_source = blocks.C.createVecRight()
        self.fe_target = fine_operator.createVecLeft()
        self.aux_target = blocks.D.createVecLeft()
        self.c_work = blocks.C.createVecLeft()
        self.h_work = blocks.H.createVecLeft()
        self.destroyed = False

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        local_fe = self.fe_source.getLocalSize()
        source_values = source.getArray(readonly=True)
        self.fe_source.getArray()[:] = source_values[:local_fe]
        self.aux_source.getArray()[:] = source_values[local_fe:]
        self.fine_operator.mult(self.fe_source, self.fe_target)
        self.blocks.C.mult(self.aux_source, self.c_work)
        self.fe_target.axpy(PETSc.ScalarType(1.0), self.c_work)
        self.blocks.D.mult(self.fe_source, self.aux_target)
        self.blocks.H.mult(self.aux_source, self.h_work)
        self.aux_target.axpy(PETSc.ScalarType(1.0), self.h_work)
        target_values = target.getArray()
        target_values[:local_fe] = self.fe_target.getArray(readonly=True)
        target_values[local_fe:] = self.aux_target.getArray(readonly=True)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self.destroyed:
            return
        self.h_work.destroy()
        self.c_work.destroy()
        self.aux_target.destroy()
        self.fe_target.destroy()
        self.aux_source.destroy()
        self.fe_source.destroy()
        self.fine_operator.destroy()
        self.blocks.destroy()
        self.destroyed = True


def create_matrix_free_augmented_operator(
    blocks: PetscCondensedBlocks,
    fine_operator: PETSc.Mat,
) -> tuple[PETSc.Mat, _AugmentedDtnMatContext]:
    """Create the action-only augmented ``[F C; D H]`` carrier."""

    if fine_operator.getSize() != (blocks.n_fe, blocks.n_fe):
        raise ValueError("fine action size does not match condensed blocks")
    local_rows = blocks.b_fe.getLocalSize() + blocks.b_aux.getLocalSize()
    size = blocks.n_fe + blocks.n_aux
    context = _AugmentedDtnMatContext(blocks, fine_operator)
    matrix = PETSc.Mat().createPython(
        ((local_rows, size), (local_rows, size)),
        context=context,
        comm=fine_operator.getComm(),
    )
    matrix.setUp()
    return matrix, context


def create_matrix_free_condensed_operator(
    blocks: PetscCondensedBlocks,
    *,
    fine_operator: PETSc.Mat | None = None,
) -> tuple[PETSc.Mat, CondensedDtnMatContext]:
    fine_operator = blocks.require_f() if fine_operator is None else fine_operator
    context = CondensedDtnMatContext(blocks, fine_operator=fine_operator)
    matrix = PETSc.Mat().createPython(
        fine_operator.getSizes(), context=context, comm=fine_operator.getComm()
    )
    matrix.setUp()
    return matrix, context


def condensed_rhs(blocks: PetscCondensedBlocks) -> PETSc.Vec:
    h_inv_b = blocks.H.createVecRight()
    h_solver = SmallDenseInverse(blocks.H)
    h_solver.solve(blocks.b_aux, h_inv_b)
    correction = blocks.C.createVecLeft()
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
    condensed = blocks.require_f().copy()
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
