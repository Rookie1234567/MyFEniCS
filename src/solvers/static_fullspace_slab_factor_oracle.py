"""Owner-local full-space slab matrix and factor inventory oracle."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Sequence

import numpy as np
import scipy.sparse as sp
from petsc4py import PETSc

from src.solvers.static_fullspace_slab_oracle import FullSpaceSlabCellRecord


_CSR_FINGERPRINT_DOMAIN = b"task037.g2.3.fullspace-slab-csr.v1"


def _dense_product(value: Any) -> np.ndarray:
    if sp.issparse(value):
        value = value.toarray()
    return np.ascontiguousarray(
        np.asarray(value, dtype=PETSc.ScalarType)
    )


def _petsc_csr_payload_bytes(matrix: PETSc.Mat) -> int:
    indptr, indices, values = matrix.getValuesCSR()
    return int(
        np.asarray(indptr).nbytes
        + np.asarray(indices).nbytes
        + np.asarray(values).nbytes
    )


def _petsc_csr_fingerprint(matrix: PETSc.Mat) -> str:
    indptr, indices, values = matrix.getValuesCSR()
    digest = hashlib.sha256()
    digest.update(_CSR_FINGERPRINT_DOMAIN)
    digest.update(b"\0")
    digest.update(np.asarray(matrix.getSize(), dtype="<i8").tobytes())
    digest.update(np.asarray(indptr, dtype="<i8").tobytes())
    digest.update(np.asarray(indices, dtype="<i8").tobytes())
    digest.update(np.asarray(values, dtype="<c16").tobytes())
    return digest.hexdigest()


def assemble_fullspace_slab_matrix(
    cells: Sequence[FullSpaceSlabCellRecord],
    *,
    active_size: int,
    trace_shift: np.ndarray | None = None,
) -> tuple[PETSc.Mat, dict[str, Any]]:
    """Assemble one owner-local full-space slab matrix on ``COMM_SELF``.

    The row/column order is all cell interiors in canonical cell-ID order,
    followed by the owner active trace rows.  Each cell contributes its four
    oriented block terms through its sparse trace expansion; no global
    uncondensed matrix is formed.
    """

    if not cells:
        raise ValueError("at least one full-space slab cell is required")
    active_size = int(active_size)
    if active_size <= 0:
        raise ValueError("active size must be positive")
    ordered_cells = tuple(sorted(cells, key=lambda cell: cell.canonical_cell_id))
    if len({cell.canonical_cell_id for cell in ordered_cells}) != len(
        ordered_cells
    ):
        raise ValueError("full-space slab cell IDs must be unique")
    shift = None
    if trace_shift is not None:
        shift = np.asarray(trace_shift, dtype=PETSc.ScalarType)
        if shift.shape != (active_size,):
            raise ValueError("trace shift must match active size")

    interior_offsets: list[int] = []
    interior_row_counts: list[int] = []
    interior_rows = 0
    for cell in ordered_cells:
        block = cell.block
        n_interior = int(block.a_ii.shape[0])
        if block.a_ii.shape != (n_interior, n_interior):
            raise ValueError("cell Aii must be square")
        if block.a_it.shape[0] != n_interior:
            raise ValueError("cell Ait rows must match Aii")
        if block.a_ti.shape[1] != n_interior:
            raise ValueError("cell Ati columns must match Aii")
        if block.a_tt.shape[0] != block.a_tt.shape[1]:
            raise ValueError("cell Att must be square")
        if cell.trace_expansion.shape[0] != block.a_tt.shape[0]:
            raise ValueError("cell C rows must match Att")
        if cell.trace_expansion.shape[1] != cell.active_positions.size:
            raise ValueError("cell C columns must match active positions")
        if np.any(cell.active_positions >= active_size):
            raise ValueError("cell active position is outside slab rows")
        interior_offsets.append(interior_rows)
        interior_row_counts.append(n_interior)
        interior_rows += n_interior

    trace_offset = interior_rows
    full_rows = trace_offset + active_size
    matrix = PETSc.Mat().createAIJ(
        size=(full_rows, full_rows),
        comm=PETSc.COMM_SELF,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    for cell, interior_offset in zip(
        ordered_cells,
        interior_offsets,
        strict=True,
    ):
        block = cell.block
        interior_indices = np.arange(
            interior_offset,
            interior_offset + block.a_ii.shape[0],
            dtype=PETSc.IntType,
        )
        trace_indices = np.asarray(
            trace_offset + cell.active_positions,
            dtype=PETSc.IntType,
        )
        expansion = cell.trace_expansion
        interior_trace = _dense_product(block.a_it @ expansion)
        trace_interior = _dense_product(expansion.conj().T @ block.a_ti)
        trace_trace = _dense_product(
            expansion.conj().T @ (block.a_tt @ expansion)
        )
        matrix.setValues(
            interior_indices,
            interior_indices,
            np.asarray(block.a_ii, dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        matrix.setValues(
            interior_indices,
            trace_indices,
            interior_trace,
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        matrix.setValues(
            trace_indices,
            interior_indices,
            trace_interior,
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        matrix.setValues(
            trace_indices,
            trace_indices,
            trace_trace,
            addv=PETSc.InsertMode.ADD_VALUES,
        )
    matrix.assemble()
    if shift is not None:
        diagonal = matrix.createVecLeft()
        matrix.getDiagonal(diagonal)
        diagonal.getArray()[trace_offset:] += shift
        matrix.setDiagonal(diagonal)
        matrix.assemble()
        diagonal.destroy()

    matrix_info = matrix.getInfo(PETSc.Mat.InfoType.LOCAL)
    audit = {
        "full_rows": int(full_rows),
        "interior_rows": int(interior_rows),
        "trace_rows": int(active_size),
        "trace_offset": int(trace_offset),
        "cell_count": int(len(ordered_cells)),
        "cell_canonical_ids": [
            int(cell.canonical_cell_id) for cell in ordered_cells
        ],
        "cell_interior_offsets": [int(value) for value in interior_offsets],
        "cell_interior_row_counts": [
            int(value) for value in interior_row_counts
        ],
        "trace_shift_applied": trace_shift is not None,
        "matrix_nnz": int(matrix_info["nz_used"]),
        "matrix_csr_payload_bytes": _petsc_csr_payload_bytes(matrix),
        "matrix_fingerprint": _petsc_csr_fingerprint(matrix),
        "matrix_fingerprint_domain": _CSR_FINGERPRINT_DOMAIN.decode("ascii"),
    }
    return matrix, audit


class FullSpaceSlabFactorOracle:
    """Own one factor matrix and work vectors after setup matrix release.

    Construction consumes the supplied setup matrix and releases it after the
    factor has been retained with its independent PETSc reference.
    """

    def __init__(
        self,
        matrix: PETSc.Mat,
        assembly_audit: dict[str, Any],
        *,
        solver: str,
    ) -> None:
        if solver not in {"ilu", "lu"}:
            raise ValueError("solver must be ilu or lu")
        self._assembly_audit = dict(assembly_audit)
        self._destroyed = False
        self._apply_count = 0
        self._apply_seconds = 0.0
        self._trace_offset = int(assembly_audit["trace_offset"])
        self._trace_rows = int(assembly_audit["trace_rows"])
        self._full_rows = int(assembly_audit["full_rows"])

        ksp = PETSc.KSP().create(PETSc.COMM_SELF)
        ksp.setOperators(matrix)
        ksp.setType("preonly")
        pc = ksp.getPC()
        if solver == "ilu":
            pc.setType("ilu")
            pc.setFactorLevels(0)
        else:
            pc.setType("lu")
        pc.setFactorOrdering("rcm")
        setup_start = time.perf_counter()
        ksp.setUp()
        setup_seconds = time.perf_counter() - setup_start
        factor_matrix = pc.getFactorMatrix()
        factor_matrix.incRef()
        factor_info = factor_matrix.getInfo(PETSc.Mat.InfoType.LOCAL)
        factor_nnz = int(factor_info["nz_used"])
        rhs = matrix.createVecRight()
        solution = matrix.createVecLeft()
        ksp.destroy()
        matrix.destroy()
        scalar_bytes = np.dtype(PETSc.ScalarType).itemsize
        index_bytes = np.dtype(PETSc.IntType).itemsize
        factor_payload_bytes = int(
            factor_nnz * (scalar_bytes + index_bytes)
            + (self._full_rows + 1) * index_bytes
        )
        self._inventory_base = {
            "solver": solver,
            "factor_ordering": "rcm",
            "ilu_level": 0 if solver == "ilu" else None,
            "full_rows": self._full_rows,
            "interior_rows": int(assembly_audit["interior_rows"]),
            "trace_rows": self._trace_rows,
            "matrix_nnz": int(assembly_audit["matrix_nnz"]),
            "matrix_csr_payload_bytes": int(
                assembly_audit["matrix_csr_payload_bytes"]
            ),
            "matrix_fingerprint": assembly_audit["matrix_fingerprint"],
            "factor_nnz": factor_nnz,
            "factor_csr_payload_bytes": factor_payload_bytes,
            "factor_csr_payload_semantics": (
                "CSR structural payload lower bound from factor NNZ and PETSc index/scalar widths; "
                "factored Mat values are not read"
            ),
            "setup_seconds": float(setup_seconds),
            "setup_matrix_lifetime": "released after factor extraction",
            "factor_lifetime": "owned by this oracle until destroy",
        }
        self._factor_matrix = factor_matrix
        self._rhs = rhs
        self._solution = solution

    @property
    def inventory(self) -> dict[str, Any]:
        """Return the current matrix/factor and apply inventory."""

        return {
            **self._inventory_base,
            "apply_count": int(self._apply_count),
            "apply_seconds": float(self._apply_seconds),
        }

    def apply_trace_rhs(self, trace_rhs: np.ndarray) -> np.ndarray:
        """Solve ``[0; trace_rhs]`` and return the full solve's trace tail."""

        if self._destroyed:
            raise RuntimeError("full-space factor oracle has been destroyed")
        rhs_values = np.asarray(trace_rhs, dtype=PETSc.ScalarType)
        if rhs_values.shape != (self._trace_rows,):
            raise ValueError("trace RHS must match trace rows")
        if not np.isfinite(rhs_values).all():
            raise ValueError("trace RHS must be finite")
        self._rhs.set(0.0)
        self._rhs.getArray()[self._trace_offset :] = rhs_values
        self._rhs.assemble()
        self._solution.set(0.0)
        start = time.perf_counter()
        self._factor_matrix.solve(self._rhs, self._solution)
        elapsed = time.perf_counter() - start
        self._apply_seconds += elapsed
        self._apply_count += 1
        result = np.asarray(
            self._solution.getArray(readonly=True)[self._trace_offset :],
            dtype=PETSc.ScalarType,
        ).copy()
        if not np.isfinite(result).all():
            raise RuntimeError("full-space factor solve returned non-finite values")
        return result

    def destroy(self) -> None:
        """Release the owned factor and work vectors exactly once."""

        if self._destroyed:
            return
        self._factor_matrix.destroy()
        self._rhs.destroy()
        self._solution.destroy()
        self._destroyed = True


__all__ = (
    "FullSpaceSlabFactorOracle",
    "assemble_fullspace_slab_matrix",
)
