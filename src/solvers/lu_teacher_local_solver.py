from __future__ import annotations

import gc
import time
from typing import Any

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .local_slab_solver import LocalCsrOperator


class SparseLuTeacherLocalSolver:
    """One-factor/many-RHS high-accuracy local sparse-LU teacher."""

    def __init__(
        self,
        operator: LocalCsrOperator,
        *,
        ordering: str = "COLAMD",
        diagonal_pivot_threshold: float = 1.0,
    ) -> None:
        self.operator_fingerprint = operator.fingerprint
        self.size = int(operator.shape[0])
        self.ordering = str(ordering)
        self.diagonal_pivot_threshold = float(diagonal_pivot_threshold)
        matrix = sp.csr_matrix(
            (operator.values, operator.indices, operator.indptr),
            shape=operator.shape,
            copy=True,
        ).tocsc()
        self.matrix_nnz = int(matrix.nnz)
        started = time.perf_counter()
        self._factor = spla.splu(
            matrix,
            permc_spec=self.ordering,
            diag_pivot_thresh=self.diagonal_pivot_threshold,
        )
        self.factorization_s = time.perf_counter() - started
        self.l_nnz = int(self._factor.L.nnz)
        self.u_nnz = int(self._factor.U.nnz)
        self.factor_nnz = self.l_nnz + self.u_nnz
        self.factor_storage_bytes = int(
            sum(
                array.nbytes
                for factor_matrix in (self._factor.L, self._factor.U)
                for array in (
                    factor_matrix.data,
                    factor_matrix.indices,
                    factor_matrix.indptr,
                )
            )
            + self._factor.perm_r.nbytes
            + self._factor.perm_c.nbytes
        )
        self.solve_count = 0
        self.solve_elapsed_s = 0.0
        self._destroyed = False

    def solve(self, rhs: np.ndarray, out: np.ndarray) -> None:
        if self._destroyed:
            raise RuntimeError("sparse-LU teacher has been destroyed")
        source = np.asarray(rhs, dtype=np.complex128)
        if source.shape != (self.size,) or out.shape != source.shape:
            raise ValueError("sparse-LU teacher rhs/output shape mismatch")
        started = time.perf_counter()
        values = np.asarray(self._factor.solve(source), dtype=np.complex128)
        self.solve_elapsed_s += time.perf_counter() - started
        if not np.all(np.isfinite(values)):
            raise RuntimeError("sparse-LU teacher returned NaN or Inf")
        out[:] = values
        self.solve_count += 1

    def solve_many(self, rhs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        source = np.asarray(rhs, dtype=np.complex128)
        if source.ndim != 2 or source.shape[1] != self.size:
            raise ValueError("sparse-LU teacher batch shape mismatch")
        output = np.empty_like(source)
        elapsed = np.empty(source.shape[0], dtype=np.float64)
        for index, row in enumerate(source):
            started = time.perf_counter()
            self.solve(row, output[index])
            elapsed[index] = time.perf_counter() - started
        return output, elapsed

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "identity": "sparse_lu_teacher",
            "operator_fingerprint": self.operator_fingerprint,
            "size": self.size,
            "matrix_nnz": self.matrix_nnz,
            "ordering": self.ordering,
            "diagonal_pivot_threshold": self.diagonal_pivot_threshold,
            "factorization_s": self.factorization_s,
            "l_nnz": self.l_nnz,
            "u_nnz": self.u_nnz,
            "factor_nnz": self.factor_nnz,
            "fill_ratio": self.factor_nnz / max(self.matrix_nnz, 1),
            "factor_storage_bytes": self.factor_storage_bytes,
            "solve_count": self.solve_count,
            "solve_elapsed_s": self.solve_elapsed_s,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._factor = None  # type: ignore[assignment]
        gc.collect()
        self._destroyed = True
